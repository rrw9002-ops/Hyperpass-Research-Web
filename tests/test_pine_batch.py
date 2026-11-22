import copy
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hyperpass import pine_batch as pb
from hyperpass import tradingview_control as tv
from hyperpass.research_desk import ResearchDesk
from hyperpass.server import Store


CODE = '//@version=6\nstrategy("Ranked scope")\nplot(close)'
REQUEST = {'engine':'pine','market':'US','mode':'custom','symbols':['AAA','BBB'],'code':CODE,'timeframe':'1D'}
LIST = {'AAA':{'name':'A','target_symbol':'NYSE:AAA'},'BBB':{'name':'B','target_symbol':'NASDAQ:BBB'}}
TARGET = {'id':'tab-one','webSocketDebuggerUrl':'fixture'}
INITIAL = {'source':'draft before the run','symbol':'NASDAQ:X','timeframe':'15','ids':['existing'], 'chart_type':1}


class Channel:
    def __init__(self):
        self.state = copy.deepcopy(INITIAL)
        self.ws = True
        self.deleted = []
        self.original_doc_edited = False
    def __enter__(self):
        return self
    def __exit__(self,*args):
        self.ws = False
    def call(self, action, params=None):
        if action == 'open_editor':
            return {'ready':True}
        if action == 'editor':
            return {'ready':True,'uri':'fixture', 'source':self.state['source']}
        if params['operation'] == 'read':
            return copy.deepcopy(self.state)
        if params['expected'] != self.state:
            return {'error':'batch_changed'}
        op = params['operation']
        if op in ('symbol','timeframe'):
            self.state[op] = params['value']
        if op == 'restore_text':
            self.state['source'] = params['original']
            return {'confirmed':True}
        if op == 'retire':
            self.deleted.append(params['study_id'])
            self.state['ids'].remove(params['study_id'])
        return {'requested':True}


class PineBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.desk = ResearchDesk(self.store)
        self.channel = Channel()
        self.symbols = []
        self.extra = lambda symbol: None
        for item in (patch('hyperpass.market_prices.pine_universe',return_value=(LIST,'listing fixture')),
                     patch.object(tv,'_select',return_value=(TARGET,[TARGET])),
                     patch.object(pb,'_BatchSession',return_value=self.channel),
                     patch.object(tv,'_run_pine',side_effect=self.strategy)):
            item.start()
            self.addCleanup(item.stop)

    def strategy(self, port, code, target, timeout, progress, expected_chart, batch_token):
        chart = self.channel.state
        self.assertEqual(chart,expected_chart)
        self.assertTrue(tv._MUTATION_LOCK.locked())
        progress({'stage':'backup','previous_source':chart['source']})
        self.assertEqual(self.desk.job(self.desk.active[0])['result']['previous_source'], INITIAL['source'])
        self.symbols.append(chart['symbol'])
        study = 'owned'+str(len(self.symbols))
        chart['source'] = code
        chart['ids'].append(study)
        self.extra(chart['symbol'])
        return {'status':'completed','study_id':study,'previous_source':'unneeded','chart':copy.deepcopy(chart),
                'report':{'study_id':study,'strategy':'Ranked scope','available':True,'metrics':{'net_profit_percent':12.3},'currency':'USD'}}

    def run_job(self, request=REQUEST):
        job = self.desk.start(request)
        deadline = time.monotonic()+10
        while self.desk.active and time.monotonic()<deadline:
            time.sleep(.015)
        self.assertIsNone(self.desk.active)
        return self.desk.job(job['id'])

    def test_separate_verified_reports_owned_cleanup_restored_draft_and_editable_saved_code(self):
        job = self.run_job()
        self.assertEqual(job['status'],'completed',job.get('error'))
        result = job['result']
        self.assertEqual((result['requested'],result['completed'],result['failed'],result['skipped']),(2,2,0,0))
        self.assertEqual(result['basis'],'independent_per_symbol')
        self.assertNotIn('total_return_pct',result)
        self.assertEqual(self.symbols,['NYSE:AAA','NASDAQ:BBB'])
        self.assertEqual(self.channel.deleted,['owned1','owned2'])
        self.assertEqual(self.channel.state,INITIAL)
        self.assertEqual(result['restore']['status'],'restored')
        reopened=ResearchDesk(self.store)
        self.assertEqual(reopened.job(job['id'])['result']['rows'],result['rows'])
        self.assertEqual(reopened.pine_report(job['id'],1)['report']['study_id'],'owned2')
        self.assertNotIn('previous_source',reopened.pine_report(job['id'],1))
        rebuilt=reopened.save_strategy({'name':'edited after test','kind':'pine','definition':dict(job['request'],code=CODE+'\nplot(open)')})
        self.assertEqual(rebuilt['definition']['symbols'],['AAA','BBB'])
        self.assertNotEqual(rebuilt['definition']['code'],job['request']['code'])

    def test_external_edit_stops_batch_without_touching_user_study(self):
        def user(symbol):
            if symbol=='NASDAQ:BBB':
                self.channel.state['ids'].append('student-study')
        self.extra=user
        job=self.run_job()
        self.assertEqual(job['status'],'partial')
        self.assertEqual((job['result']['completed'],job['result']['failed']),(1,1))
        self.assertEqual(job['result']['restore']['status'],'unconfirmed')
        self.assertIn('student-study',self.channel.state['ids'])
        self.assertIsNotNone(self.desk.pine_report(job['id'],0))
        self.assertIsNone(self.desk.pine_report(job['id'],1))

    def test_cancel_keeps_finished_report_and_restores_chart(self):
        self.extra=lambda _symbol:self.desk.cancel(self.desk.active[0])
        job=self.run_job()
        self.assertEqual(job['status'],'cancelled')
        self.assertEqual(job['result']['not_attempted'],1)
        self.assertEqual(len(job['result']['rows']),1)
        self.assertEqual(self.channel.state,INITIAL)

    def test_unknown_exchange_counted_and_never_guessed(self):
        candidates=dict(LIST,NOPE={'name':'Unknown','target_symbol':None})
        with patch('hyperpass.market_prices.pine_universe',return_value=(candidates,'test')):
            job=self.run_job(dict(REQUEST,mode='market',symbols=[]))
        self.assertEqual(job['status'],'partial')
        self.assertEqual(job['result']['skipped'],1)
        self.assertEqual(job['result']['rows'][-1]['symbol'],'NOPE')
        self.assertIsNone(job['result']['rows'][-1]['target_symbol'])
        self.assertEqual(len(self.symbols),2)

    def test_invalid_scope_and_foreign_engine_options_rejected(self):
        for keys in ({'mode':'market'}, {'timeframe':'13'}, {'port':80}, {'target_id':'bad?'},
                     {'settings':{'initial_capital':100}}, {'code':'//@version=6\nindicator("wrong")'}):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                pb.validate(dict(REQUEST,**keys))


@unittest.skipUnless(shutil.which('node'),'Node optional for page adapter verification')
class PinePageGuardTests(unittest.TestCase):
    def test_cleanup_only_removes_one_new_verified_id_while_original_and_draft_are_untouched(self):
        program = """
const run = PROGRAM;
let removed = [], ids = ['existing','ours'], source = 'pine';
const ed = {getValue:()=>source,setValue:v=>source=v,getDomNode:()=>el};
const el = {__reactFiber$test:{memoizedProps:{value:{monacoEnv:{editor:{getEditors:()=>[ed]}}}}},contains:()=>true};
global.document={querySelector:()=>el,querySelectorAll:()=>[]};
const chart = {getAllStudies:()=>ids.map(id=>({id})),symbol:()=>'NASDAQ:AAA',resolution:()=>'1D',
 chartType:()=>1,removeEntity:id=>{removed.push(id);ids=ids.filter(x=>x!==id)},
 _chartWidget:{model:()=>({model:()=>({dataSources:()=>ids.map(id=>({id:()=>id,metaInfo:()=>({is_strategy:true}),reportData:()=>({})}))})})}};
global.window={TradingViewApi:{_activeChartWidgetWV:{value:()=>chart}},__hyperpassResearchRun:{token:'x',kind:'strategy',source,refs:{existing:{}}}};
(async()=>{
document.body={innerText:'Log in'};
if((await run('batch',{operation:'read'})).login_prompt) throw Error('Menu login link misidentified');
document.body.innerText='Log in\\nContinue with Google\\nDo not have an account? Sign up';
if(!(await run('batch',{operation:'read'})).login_prompt || !(await run('run_state',{batch:true,token:'x'})).login_required) throw Error('Guest login request not detected');
document.body.innerText='';
let expected=await run('batch',{operation:'read'});
let args={operation:'retire',token:'x',expected,study_id:'ours'};
if(!(await run('batch',{...args,token:'wrong'})).error) throw Error('Wrong token accepted');
if(!(await run('batch',{...args,study_id:'existing'})).error) throw Error('Existing entity accepted');
source='student changed';
if(!(await run('batch',args)).error) throw Error('Edited source accepted');
source='pine';
if(removed.length || !(await run('batch',args)).requested || removed.join(',')!=='ours' || ids.join(',')!=='existing') throw Error('Owned cleanup failed');
})().catch(e=>{console.error(e);process.exit(1)});
""".replace('PROGRAM','('+pb._BatchSession.program+')')
        subprocess.run(['node','-'],input=program,text=True,encoding='utf8',capture_output=True,check=True)
