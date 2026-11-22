"""User-facing workspace HTTP contracts, using labelled synthetic chart data.

These tests do not contact market-data or paid AI services.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import math
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hyperpass.server import Application, Store, serve


def synthetic_packet():
    start=datetime(2024,1,1,tzinfo=timezone.utc)
    rows=[]
    for index in range(120):
        price=100+index*.1+8*math.sin(index/8)
        rows.append({'timestamp':(start+timedelta(days=index)).isoformat(),
                     'open':price,'high':price+1,'low':price-1,'close':price,'volume':1000})
    return {'provider':'synthetic-test-fixture','symbol':'TEST','timeframe':'1d',
            'currency':'USD','as_of':rows[-1]['timestamp'],'retrieved_at':'2024-05-01T00:00:00+00:00',
            'source_url':'https://example.invalid/synthetic-test-only',
            'warning':'Synthetic test fixture. Not observed market data.', 'records':rows}


class WorkspaceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.app=Application(self.folder.name)
        self.server=serve(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.app.stop_event.set()
        deadline=time.monotonic()+3
        while self.app.active and time.monotonic()<deadline: time.sleep(.01)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.folder.cleanup()

    def request(self,path,payload=None,headers=None):
        request_headers={'Content-Type':'application/json','X-CSRF-Token':self.app.csrf}
        request_headers.update(headers or {})
        request=Request(self.base+path,headers=request_headers,
                        data=json.dumps(payload).encode() if payload is not None else None)
        try: response=urlopen(request,timeout=5)
        except HTTPError as error: response=error
        with response:
            raw=response.read().decode('utf-8')
            data=json.loads(raw) if 'application/json' in response.headers.get('Content-Type','') else raw
            return response.status,response.headers,data

    def create_chart(self):
        source=synthetic_packet()
        options={'strategy':'trend_breakout','fast_period':5,'slow_period':10,'breakout_period':5,
                 'initial_capital':10000,'fee_bps':5,'slippage_bps':5}
        with patch.object(self.app.sources,'chart_history',return_value=source):
            status,_,chart=self.request('/api/charts',{'source':'yahoo','symbol':'TEST','period':'2y','interval':'1d','options':options})
        self.assertEqual(status,201,chart)
        return source,options,chart

    def wait_for_run(self,identity):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            status,_,run=self.request('/api/runs/'+identity)
            self.assertEqual(status,200)
            if run['status'] not in ('queued','running','collecting') and not self.app.active: return run
            time.sleep(.01)
        self.fail('Research request did not finish')

    def test_expanded_chart_view_derives_legacy_series_without_changing_saved_experiment(self):
        _, _, created = self.create_chart()
        old = copy.deepcopy(created)
        old['id'] = 'd' * 32
        old['settings']['indicators'] = ['rsi']
        old['indicators'] = {'rsi': old['indicators']['rsi']}
        old['evidence_summary']['latest_indicators'] = {'rsi': old['indicators']['rsi'][-1]}
        self.app.store.put_chart(old)
        url = '/api/charts/' + old['id']
        with patch.object(self.app.sources, 'chart_history', side_effect=AssertionError('Unexpected quote request')):
            status, _, expanded = self.request(url + '?view=chart')
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(expanded['indicators']), 29)
        self.assertEqual(expanded['indicators']['rsi'], old['indicators']['rsi'])
        for name, series in expanded['indicators'].items():
            self.assertEqual(len(series), len(old['candles']))
            self.assertEqual(series[-1], expanded['evidence_summary']['latest_indicators'][name])
        for key in ('id','settings','candles','backtest','source_packet','created_at','provenance'):
            self.assertEqual(expanded[key], old[key])
        self.assertEqual(self.request(url + '/export')[2], old)
        self.assertEqual(self.app.store.get_chart(old['id']), old)

    def test_chart_is_saved_and_retrievable_with_source_settings_and_exports(self):
        source,options,created=self.create_chart()
        status,_,loaded=self.request('/api/charts/'+created['id'])
        self.assertEqual(status,200)
        self.assertEqual(loaded['source_packet'],source)
        for name,value in options.items(): self.assertEqual(loaded['settings'][name],value)
        self.assertEqual(len(loaded['candles']),120)
        self.assertTrue(loaded['backtest']['equity'])
        status,headers,exported=self.request('/api/charts/'+created['id']+'/export')
        self.assertEqual(status,200)
        self.assertIn('attachment',headers.get('Content-Disposition',''))
        self.assertEqual(exported,loaded)
        status,headers,pine=self.request('/api/charts/'+created['id']+'/pine')
        self.assertEqual(status,200)
        self.assertIn('attachment',headers.get('Content-Disposition',''))
        self.assertTrue(pine.startswith('//@version=6'))
        restored=Store(self.folder.name).get_chart(created['id'])
        self.assertEqual(restored['source_packet'],source)
        self.assertEqual(restored['evidence_summary'],loaded['evidence_summary'])
        library=self.request('/api/library')[2]
        self.assertEqual(library['counts']['charts'],1)
        self.assertEqual(library['counts']['reports'],0)
        self.assertEqual(library['items'][0]['id'],created['id'])

    def test_selected_agent_receives_stored_chart_evidence_and_preserves_link(self):
        _,_,chart=self.create_chart()
        self.app.provider=object()  # An in-process test double; no key or network.
        completed={'status':'completed','report':'Synthetic integration result, not AI research.',
                   'report_complete':True,'artifacts':[], 'usage':{'calls':0},
                   'progress':{'percent':100,'stage':'completed','label':'Test complete','estimated':True}}
        with patch('hyperpass.server.Engine') as engine:
            engine.return_value.run.return_value=completed
            code,_,started=self.request('/api/runs',{'question':'Explain the selected chart test.',
                        'target_role':'technical-analyst','chart_id':chart['id'],'mode':'live',
                        'category':'stock','web_search':False,'evidence':'User-provided fixture context.',
                        'chart_summary':'CLIENT-FORGED-SUMMARY-MUST-NOT-BE-TRUSTED'})
            self.assertEqual(code,202,started)
            saved=self.wait_for_run(started['id'])
            supplied=engine.return_value.run.call_args.kwargs
        self.assertEqual(supplied['target_role'],'technical-analyst')
        self.assertIn(chart['evidence_summary']['provenance']['ohlcv_sha256'],supplied['evidence'])
        self.assertIn('User-provided fixture context.',supplied['evidence'])
        self.assertNotIn('CLIENT-FORGED',supplied['evidence'])
        self.assertEqual(saved['chart_id'],chart['id'])
        self.assertEqual(saved['target_role'],'technical-analyst')
        self.assertEqual(saved['status'],'completed')

    def test_missing_chart_or_invalid_agent_is_rejected_before_model_work(self):
        self.app.provider=object()
        with patch('hyperpass.server.Engine') as engine:
            for fields in ({'chart_id':'missing'}, {'chart_id':'f'*32},
                           {'target_role':'not-an-agent'}, {'target_role':'judgment-reviewer'}):
                with self.subTest(fields=fields):
                    code,_,body=self.request('/api/runs',{'question':'Test only','mode':'live',**fields})
                    self.assertEqual(code,400,body)
                    self.assertIn('error',body)
            engine.assert_not_called()
        self.assertEqual(self.app.store.list_full(),[])

    def test_library_separates_completed_reports_incomplete_runs_and_samples(self):
        accepted={'id':'fundamental-analyst-v1','role':'fundamental-analyst','state':'accepted'}
        records=[('a','live','completed',True,[accepted]),
                 ('b','live','blocked',False,[accepted]),
                 ('c','demo','completed',True,[accepted])]
        for letter,mode,status,complete,artifacts in records:
            self.app.store.put({'id':letter*32,'question':'Synthetic library fixture','mode':mode,
                                'status':status,'report_complete':complete,'report':'Test-only record.',
                                'created_at':'2024-01-01T00:00:00+00:00','artifacts':artifacts})
        code,_,library=self.request('/api/library')
        self.assertEqual(code,200)
        self.assertEqual(library['counts'],{'reports':1,'charts':0,'artifacts':1,'incomplete':1,'samples':1})
        self.assertEqual({item['type'] for item in library['items']},{'report','incomplete','sample'})

    def test_bad_chart_source_or_price_data_does_not_save_a_completed_chart(self):
        fixture=synthetic_packet()
        broken=copy.deepcopy(fixture)
        broken['records'][50]['open']=None
        with patch.object(self.app.sources,'chart_history',return_value=broken):
            code,_,body=self.request('/api/charts',{'source':'yahoo','symbol':'TEST'})
            self.assertEqual(code,400)
            self.assertIn('51번째 봉',body['error'])
        for payload in ({'source':'broker-orders','symbol':'TEST'},
                        {'source':'csv','symbol':'TEST','csv':'time,close\n2024-01-01,10\n2024-01-02,11'}):
            self.assertEqual(self.request('/api/charts',payload)[0],400)
        with patch.object(self.app.sources,'chart_history') as fetch:
            self.assertEqual(self.request('/api/charts',{'source':'yahoo','symbol':'TEST'},
                                          {'X-CSRF-Token':'invalid'})[0],403)
            fetch.assert_not_called()
        self.assertEqual(self.app.store.list_charts(),[])
        self.assertEqual(self.request('/api/library')[2]['counts']['charts'],0)

    def test_workspace_static_assets_are_served_as_usable_resource_types(self):
        for path,media in (('/brain.js','javascript'),('/chart.js','javascript'),('/chart.css','text/css')):
            with self.subTest(path=path):
                code,headers,body=self.request(path)
                self.assertEqual(code,200)
                self.assertIn(media,headers.get('Content-Type',''))
                self.assertGreater(len(body),100)
        self.assertEqual(self.request('/api/charts/'+'e'*32)[0],404)
        with urlopen(self.base + '/fonts/PretendardVariable.woff2') as font:
            self.assertEqual(font.headers['Content-Type'], 'font/woff2')
            self.assertEqual(font.read(4), b'wOF2')
        with urlopen(self.base + '/fonts/OFL.txt') as license_file:
            self.assertIn(b'SIL Open Font License', license_file.read())


if __name__ == '__main__': unittest.main()
