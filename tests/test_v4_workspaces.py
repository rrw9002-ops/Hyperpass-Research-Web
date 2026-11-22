"""HTTP integration checks with isolated team files and synthetic connector/AI results.

No real AI, TradingView process, market network, account, or student configuration
is used. Each case owns its runtime and editable team directory.
"""
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from hyperpass.server import Application, serve


def completed_research():
    return {'status':'completed','report':'Synthetic HTTP test result; not live AI analysis.',
            'report_complete':True,'artifacts':[],'usage':{'calls':0},
            'progress':{'percent':100,'stage':'completed','label':'Test fixture complete','estimated':True}}


def strategy_fixture():
    return {'status':'completed','chart':{'symbol':'TEST:FIXTURE','timeframe':'1D','studies':[]},
            'study_id':'test-strategy-id',
            'report':{'strategy':'Synthetic integration fixture, not a TradingView observation',
                      'study_id':'test-strategy-id','currency':'TEST',
                      'metrics':{'net_profit':123.45,'total_trades':3,'max_drawdown':None},
                      'settings':{'fixture_only':True},'trades':[],'orders':[],'equity':[],
                      'notes':['Synthetic data for HTTP integration testing.']},
            'warnings':['Synthetic connector fixture; no TradingView request was sent.']}


class V4WorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.app=Application(self.root/'runtime',team_dir=self.root/'team')
        self.server=serve(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.app.stop_event.set()
        deadline=time.monotonic()+5
        while (self.app.active or self.app.tv_jobs.active) and time.monotonic()<deadline:
            time.sleep(.01)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.folder.cleanup()

    def request(self,path,payload=None,headers=None):
        request_headers={'Content-Type':'application/json','X-CSRF-Token':self.app.csrf}
        request_headers.update(headers or {})
        request=Request(self.base+path,headers=request_headers,
                        data=json.dumps(payload).encode('utf-8') if payload is not None else None)
        try:
            response=urlopen(request,timeout=8)
        except HTTPError as error:
            response=error
        with response:
            raw=response.read().decode('utf-8')
            data=json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
            return response.status,response.headers,data

    def document(self,path='roles/news-analyst.md'):
        code,_,document=self.request('/api/team/document?path='+quote(path,safe=''))
        self.assertEqual(code,200,document)
        return document

    def wait_job(self,identity):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            code,_,job=self.request('/api/tradingview/jobs/'+identity)
            self.assertEqual(code,200,job)
            if job['status'] in ('completed','failed','cancelled') and self.app.tv_jobs.active is None:
                return job
            time.sleep(.01)
        self.fail('TradingView fixture worker did not finish')

    def wait_run(self,identity):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            code,_,run=self.request('/api/runs/'+identity)
            self.assertEqual(code,200,run)
            if run['status'] not in ('queued','running','collecting') and self.app.active is None:
                return run
            time.sleep(.01)
        self.fail('Research fixture worker did not finish')

    def save_document(self,document,content):
        return self.request('/api/team/document',{'path':document['path'],'content':content,
                                                  'expected_revision':document['revision']})

    def test_team_catalog_edit_revision_conflict_and_backup(self):
        code,_,catalog=self.request('/api/team')
        self.assertEqual(code,200)
        self.assertEqual(len(catalog['documents']),33)
        self.assertEqual(Path(catalog['team_dir']),self.root/'team')
        self.assertEqual({row['kind'] for row in catalog['documents']},{'common','role','skill','reference'})
        self.assertTrue(all('content' not in row for row in catalog['documents']))
        original=self.document()
        content=original['content']+'\nHTTP fixture edit: distinguish confirmed news from interpretation.\n'
        code,_,saved=self.save_document(original,content)
        self.assertEqual(code,200,saved)
        self.assertEqual(saved['content'],content)
        self.assertNotEqual(saved['revision'],original['revision'])
        self.assertEqual((self.root/'team'/original['path']).read_text(encoding='utf-8'),content)
        backup=self.root/'team/.history/roles'/('news-analyst-'+original['revision']+'.md')
        self.assertEqual(backup.read_text(encoding='utf-8'),original['content'])
        code,_,conflict=self.save_document(original,'Stale edit must not overwrite newer content.')
        self.assertEqual(code,409,conflict)
        self.assertEqual(self.document()['content'],content)
        # A direct editor change is observed by the same HTTP read API.
        external=content.replace('\r\n','\n').replace('\n','\r\n')+'\r\nExternal editor fixture change.\r\n'
        (self.root/'team'/original['path']).write_bytes(external.encode('utf-8'))
        reopened=self.document()
        self.assertEqual(reopened['content'],external)
        self.assertNotEqual(reopened['revision'],saved['revision'])

    def test_team_path_and_csrf_failures_cannot_write_files(self):
        original=self.document()
        outside=self.root/'outside.md'
        outside.write_text('Unchanged outside fixture',encoding='utf-8')
        for path in ('../outside.md','roles/../../outside.md','roles/new-unapproved-role.md',str(outside)):
            with self.subTest(path=path):
                self.assertEqual(self.request('/api/team/document?path='+quote(path,safe=''))[0],400)
                self.assertEqual(self.request('/api/team/document',{'path':path,'content':'Rejected fixture',
                                  'expected_revision':original['revision']})[0],400)
        code,_,body=self.request('/api/team/document',{'path':original['path'],'content':'Rejected CSRF write',
                            'expected_revision':original['revision']},{'X-CSRF-Token':''})
        self.assertEqual(code,403,body)
        self.assertEqual(outside.read_text(encoding='utf-8'),'Unchanged outside fixture')
        self.assertEqual(self.document()['content'],original['content'])

    def test_run_freezes_team_snapshot_and_next_run_reads_saved_changes(self):
        self.app.provider=object()  # No network transport is constructed or used.
        original=self.document()
        entered=threading.Event()
        release=threading.Event()
        def research(*args,**kwargs):
            entered.set()
            if not release.wait(4): raise RuntimeError('Test synchronization timed out')
            return completed_research()
        payload={'question':'Synthetic instruction snapshot test','mode':'live','web_search':False,
                 'evidence':'Synthetic research input. Not financial evidence.','target_role':'news-analyst',
                 'team_snapshot':{'documents':{'common.md':'CLIENT-FORGED-INSTRUCTIONS'}}}
        with patch('hyperpass.server.Engine') as engine:
            engine.return_value.run.side_effect=research
            code,_,started=self.request('/api/runs',payload)
            self.assertEqual(code,202,started)
            try:
                self.assertTrue(entered.wait(2))
                changed=original['content']+'\nNEXT-RUN-ONLY-FIXTURE\n'
                code,_,saved=self.save_document(original,changed)
                self.assertEqual(code,200,saved)
                running=self.request('/api/runs/'+started['id'])[2]
                self.assertEqual(running['team_snapshot']['documents'][original['path']],original['content'])
                self.assertNotIn('CLIENT-FORGED-INSTRUCTIONS',json.dumps(running['team_snapshot']))
                passed=engine.call_args.kwargs['team_snapshot']
                self.assertEqual(passed['documents'][original['path']],original['content'])
            finally:
                release.set()
            first=self.wait_run(started['id'])
            engine.return_value.run.side_effect=None
            engine.return_value.run.return_value=completed_research()
            code,_,next_started=self.request('/api/runs',payload)
            self.assertEqual(code,202,next_started)
            second=self.wait_run(next_started['id'])
        self.assertEqual(first['team_snapshot']['documents'][original['path']],original['content'])
        self.assertEqual(second['team_snapshot']['documents'][original['path']],changed)
        self.assertNotEqual(first['team_snapshot']['revision'],second['team_snapshot']['revision'])
        with self.app.store.connect() as db:
            persisted=json.loads(db.execute('SELECT body FROM runs WHERE id=?',(first['id'],)).fetchone()[0])
        self.assertEqual(persisted['team_snapshot'],first['team_snapshot'])

    def test_tradingview_jobs_are_serialized_persisted_and_exportable(self):
        entered=threading.Event()
        release=threading.Event()
        result={'status':'configured','changed':['Synthetic indicator fixture'],'chart':{'symbol':'TEST:FIXTURE'},
                'warnings':['No TradingView connection was used in this test.']}
        def configure(**kwargs):
            entered.set()
            if not release.wait(4): raise RuntimeError('Test synchronization timed out')
            return copy.deepcopy(result)
        payload={'action':'configure','port':9222,'target_id':'fixture-target','symbol':'TEST:FIXTURE',
                 'timeframe':'1D','indicators':[{'name':'Moving Average','inputs':{'length':20}}]}
        with patch('hyperpass.tradingview_control.configure_chart',side_effect=configure) as control:
            code,_,started=self.request('/api/tradingview/jobs',payload)
            self.assertEqual(code,202,started)
            try:
                self.assertTrue(entered.wait(2))
                self.assertEqual(self.request('/api/tradingview/jobs',payload)[0],400)
                self.assertEqual(control.call_count,1)
            finally:
                release.set()
            saved=self.wait_job(started['id'])
            self.assertEqual(control.call_args.kwargs['indicators'],payload['indicators'])
            self.assertEqual(control.call_args.kwargs['target_id'],'fixture-target')
        self.assertEqual(saved['status'],'completed')
        self.assertEqual(saved['result'],result)
        code,headers,exported=self.request('/api/tradingview/jobs/'+saved['id']+'/export')
        self.assertEqual(code,200)
        self.assertIn('attachment',headers.get('Content-Disposition',''))
        self.assertEqual(exported,saved)
        code,_,listing=self.request('/api/tradingview/jobs')
        self.assertEqual(code,200)
        row=next(item for item in listing['jobs'] if item['id']==saved['id'])
        self.assertEqual(row['action'],'configure')
        self.assertEqual(row['symbol'],'TEST:FIXTURE')
        self.assertNotIn('request',row)
        self.assertNotIn('result',row)
        with self.app.store.connect() as db:
            persisted=json.loads(db.execute('SELECT body FROM tradingview_jobs WHERE id=?',(saved['id'],)).fetchone()[0])
        self.assertEqual(persisted,saved)

    def test_backtest_compile_error_and_exception_keep_original_source_backup(self):
        payload={'action':'backtest','port':9222,'symbol':'TEST:FIXTURE','timeframe':'1D',
                 'indicators':[{'name':'Moving Average','inputs':{'length':20}}],
                 'code':'//@version=6\nstrategy("Synthetic test only")'}
        for crashes in (False,True):
            with self.subTest(crashes=crashes):
                def run_strategy(**kwargs):
                    kwargs['on_progress']({'stage':'source_backed_up','message':'Test backup recorded',
                                           'previous_source':'ORIGINAL-EDITOR-CODE-FIXTURE'})
                    if crashes: raise OSError('Synthetic compile transport failure')
                    return {'status':'compile_error','compile_errors':['Synthetic compiler error'],
                            'warnings':['Synthetic fixture only; not an actual Pine compilation.']}
                with patch('hyperpass.tradingview_control.configure_chart',return_value={'status':'configured'}) as configure, \
                     patch('hyperpass.tradingview_control.run_strategy',side_effect=run_strategy):
                    code,_,started=self.request('/api/tradingview/jobs',payload)
                    self.assertEqual(code,202,started)
                    saved=self.wait_job(started['id'])
                    self.assertEqual(configure.call_args.kwargs['indicators'],payload['indicators'])
                self.assertEqual(saved['status'],'failed')
                self.assertEqual(saved['previous_source'],'ORIGINAL-EDITOR-CODE-FIXTURE')
                self.assertIsNotNone(saved['finished_at'])
                exported=self.request('/api/tradingview/jobs/'+saved['id']+'/export')[2]
                self.assertEqual(exported['previous_source'],'ORIGINAL-EDITOR-CODE-FIXTURE')
                if not crashes:
                    self.assertEqual(saved['result']['status'],'compile_error')
                    self.assertEqual(saved['result']['compile_errors'],['Synthetic compiler error'])
                self.assertEqual(self.app.tv_jobs.active,None)
                row=next(item for item in self.request('/api/tradingview/jobs')[2]['jobs'] if item['id']==saved['id'])
                self.assertNotIn('previous_source',row)

    def test_backtest_does_not_run_after_partial_chart_configuration(self):
        partial={'status':'partial','warnings':['Synthetic symbol selection failed'],
                 'chart':{'symbol':'WRONG:FIXTURE','timeframe':'1D'}}
        with patch('hyperpass.tradingview_control.configure_chart',return_value=partial), \
             patch('hyperpass.tradingview_control.run_strategy',return_value=strategy_fixture()) as strategy:
            code,_,started=self.request('/api/tradingview/jobs',{'action':'backtest','port':9222,
                      'symbol':'TEST:FIXTURE','timeframe':'1D','code':'strategy("Test fixture")'})
            self.assertEqual(code,202,started)
            saved=self.wait_job(started['id'])
            self.assertEqual(saved['status'],'failed')
            strategy.assert_not_called()

    def test_saved_backtest_evidence_is_attached_without_client_forgery_or_editor_backup(self):
        result=strategy_fixture()
        result['previous_source']='PRIVATE-EDITOR-BACKUP-MUST-NOT-BECOME-EVIDENCE'
        with patch('hyperpass.tradingview_control.configure_chart',return_value={'status':'configured'}), \
             patch('hyperpass.tradingview_control.run_strategy',return_value=result):
            code,_,created=self.request('/api/tradingview/jobs',{'action':'backtest','port':9222,
                     'symbol':'TEST:FIXTURE','code':'strategy("Synthetic connector test")'})
            self.assertEqual(code,202,created)
            backtest=self.wait_job(created['id'])
        self.app.provider=object()
        with patch('hyperpass.server.Engine') as engine:
            engine.return_value.run.return_value=completed_research()
            code,_,started=self.request('/api/runs',{'mode':'live','question':'Interpret the synthetic backtest fixture',
                'web_search':False,'target_role':'technical-analyst','tv_job_id':backtest['id'],
                'tv_result':{'report':'CLIENT-FORGED-REPORT'},'team_snapshot':{'documents':{'fake':'CLIENT-FORGED-TEAM'}}})
            self.assertEqual(code,202,started)
            saved=self.wait_run(started['id'])
            supplied=engine.return_value.run.call_args.kwargs
        self.assertEqual(saved['tv_job_id'],backtest['id'])
        self.assertEqual(supplied['target_role'],'technical-analyst')
        self.assertIn('test-strategy-id',supplied['evidence'])
        self.assertIn('123.45',supplied['evidence'])
        self.assertNotIn('CLIENT-FORGED',supplied['evidence'])
        self.assertNotIn('PRIVATE-EDITOR-BACKUP',supplied['evidence'])
        self.assertNotIn('CLIENT-FORGED-TEAM',json.dumps(saved['team_snapshot']))

    def test_failed_missing_or_non_backtest_job_cannot_be_attached(self):
        fixture=strategy_fixture()
        for letter,status,action in (('a','failed','backtest'),('b','completed','configure'),('c','running','backtest')):
            self.app.tv_jobs.put({'id':letter*32,'status':status,'stage':'fixture','created_at':'2024-01-01T00:00:00+00:00',
                                'request':{'action':action,'symbol':'TEST:FIXTURE'},'result':fixture,'error':None})
        self.app.provider=object()
        with patch('hyperpass.server.Engine') as engine:
            for identity in ('a'*32,'b'*32,'c'*32,'f'*32,'../../outside'):
                with self.subTest(identity=identity):
                    code,_,body=self.request('/api/runs',{'mode':'live','question':'Synthetic attachment refusal test',
                                        'web_search':False,'tv_job_id':identity})
                    self.assertEqual(code,400,body)
            engine.assert_not_called()
        self.assertEqual(self.app.store.list_full(),[])

    def test_connection_status_target_selection_and_static_routes(self):
        observed={'connected':True,'chart':{'symbol':'TEST:FIXTURE','timeframe':'1D','studies':[]},
                  'targets':[{'id':'test-target','title':'Synthetic target only'}]}
        with patch('hyperpass.tradingview_control.status',return_value=observed) as status:
            code,_,body=self.request('/api/tradingview/status?port=9333&target_id=test-target')
            self.assertEqual(code,200)
            self.assertEqual(body,observed)
            status.assert_called_once_with(port=9333,target_id='test-target')
        for path,media in (('/team.js','javascript'),('/tradingview.js','javascript'),('/workspaces.css','text/css')):
            with self.subTest(path=path):
                code,headers,body=self.request(path)
                self.assertEqual(code,200)
                self.assertIn(media,headers.get('Content-Type',''))
                self.assertGreater(len(body),100)
        self.assertEqual(self.request('/api/tradingview/jobs/'+'e'*32)[0],404)
        with patch('hyperpass.tradingview_control.configure_chart') as configure:
            code,_,body=self.request('/api/tradingview/jobs',{'action':'configure','port':9222},
                                     {'X-CSRF-Token':'not-valid'})
            self.assertEqual(code,403,body)
            configure.assert_not_called()
        self.assertEqual(self.app.tv_jobs.list(),[])


if __name__=='__main__': unittest.main()
