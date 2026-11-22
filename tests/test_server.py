import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from hyperpass.server import Application, Store, serve, evidence_excerpt

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Application(self.temp.name)
        self.server=serve(self.app,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.app.stop_event.set()
        for _ in range(100):
            if not self.app.active: break
            time.sleep(.02)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def call(self,path,payload=None,headers=None):
        h={'Content-Type':'application/json','X-CSRF-Token':self.app.csrf}
        if headers: h.update(headers)
        req=Request(self.url+path,data=json.dumps(payload).encode() if payload is not None else None,headers=h)
        try:
            with urlopen(req,timeout=10) as r:
                return r.status,json.loads(r.read())
        except HTTPError as e:
            with e: return e.code,json.loads(e.read())

    def test_csrf_host_origin_and_traversal(self):
        for headers in ({'X-CSRF-Token':'bad'},{'Origin':'https://evil.example'},{'Host':'evil.example'}):
            self.assertEqual(self.call('/api/runs',{'question':'test','mode':'demo'},headers)[0],403)
        self.assertEqual(self.call('/../app.py')[0],404)
        self.assertEqual(self.call('/api/status',headers={'Host':'evil.example'})[0],403)

    def test_live_requires_verified_key_and_invalid_limits_rejected(self):
        self.assertEqual(self.call('/api/runs',{'question':'test'})[0],400)
        self.assertEqual(self.call('/api/runs',{'question':'test','mode':'demo','max_calls':100})[0],400)
        self.assertEqual(self.call('/api/runs',{'question':'test','mode':'demo','providers':['broker-order']})[0],400)

    def test_key_never_returned_or_saved(self):
        secret='sk-test-super-private-sentinel'
        with patch('hyperpass.server.OpenAIProvider') as cls:
            cls.return_value.check.return_value={'ok':True}
            status,result=self.call('/api/connect',{'api_key':secret,'model':'gpt-5-mini'})
            self.assertEqual(status,200)
            self.assertTrue(result['connected'])
        self.assertNotIn(secret,json.dumps(self.call('/api/status')))
        for path in Path(self.temp.name).rglob('*'):
            if path.is_file(): self.assertNotIn(secret.encode(),path.read_bytes())
        self.assertEqual(self.call('/api/disconnect',{})[0],200)
        self.assertFalse(self.call('/api/status')[1]['connected'])

    def test_failed_connect_is_not_connected(self):
        from hyperpass.engine import ProviderError
        with patch('hyperpass.server.OpenAIProvider') as cls:
            cls.return_value.check.side_effect=ProviderError('인증 실패')
            self.assertEqual(self.call('/api/connect',{'api_key':'sk-test-invalid-key'})[0],400)
        self.assertFalse(self.app.status()['connected'])

    def test_demo_is_explicit_persists_and_exports(self):
        code,result=self.call('/api/runs',{'question':'샘플 검사','mode':'demo','max_calls':12})
        self.assertEqual(code,202)
        for _ in range(200):
            run=self.call('/api/runs/'+result['id'])[1]
            if run['status'] not in ('queued','running','collecting'): break
            time.sleep(.05)
        self.assertEqual(run['mode'],'demo')
        self.assertEqual(run['status'],'completed',run.get('error',run))
        self.assertTrue(run['report'])
        self.assertTrue(run['events'])
        with urlopen(self.url+'/api/runs/'+result['id']+'/export') as r:
            self.assertIn(b'demo',r.read())
        self.assertEqual(Store(self.temp.name).get(result['id'])['report'],run['report'])

    def test_restart_marks_unfinished_run_interrupted(self):
        self.app.store.put({'id':'a'*32,'status':'running'})
        run=Store(self.temp.name).get('a'*32)
        self.assertEqual(run['status'],'interrupted')
        self.assertEqual(run['progress']['stage'],'interrupted')
        self.assertIsNone(run['progress']['percent'])  # Do not invent progress for old records.
        self.assertFalse(run['report_complete'])
        self.assertEqual(run['events'][-1]['progress'],run['progress'])

    def test_restart_preserves_progress_but_never_claims_completion(self):
        for index,percent in enumerate((72,100)):
            with self.subTest(percent=percent):
                run_id=str(index)*32
                self.app.store.put({'id':run_id,'status':'running','report_complete':True,
                    'progress':{'percent':percent,'stage':'reviewing','label':'검토 중',
                                'calls_completed':6,'call_limit':12,'current_role':'judgment-reviewer'}})
                run=Store(self.temp.name).get(run_id)
                self.assertEqual(run['progress']['percent'],min(95,percent))
                self.assertEqual(run['progress']['stage'],'interrupted')
                self.assertEqual(run['progress']['calls_completed'],6)
                self.assertEqual(run['progress']['current_role'],'judgment-reviewer')
                self.assertFalse(run['report_complete'])
                self.assertTrue(run['finished_at'])
                self.assertEqual(run['events'][-1]['status'],'interrupted')

    def test_source_success_needed_before_marking_configured(self):
        with patch.object(self.app.sources,'configure'),patch.object(self.app.sources,'disconnect'),patch.object(self.app.sources,'fetch',side_effect=RuntimeError('private-key')):
            status,result=self.call('/api/sources/fmp',{'config':{'api_key':'private-key'}})
        self.assertEqual(status,400)
        self.assertNotIn('private-key',str(result))
        self.assertFalse(next(s for s in self.app.source_catalog() if s['id']=='fmp')['configured'])

    def test_connections_do_not_hold_status_lock(self):
        entered=threading.Event()
        release=threading.Event()
        def slow_check():
            entered.set()
            release.wait(3)
        with patch('hyperpass.server.OpenAIProvider') as cls:
            cls.return_value.check.side_effect=slow_check
            worker=threading.Thread(target=lambda:self.call('/api/connect',{'api_key':'sk-test-private-key'}))
            worker.start()
            self.assertTrue(entered.wait(2))
            started=time.monotonic()
            self.assertEqual(self.call('/api/status')[0],200)
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual(self.call('/api/runs',{'question':'test','mode':'demo'})[0],400)
            release.set()
            worker.join(3)

    def test_fetched_data_excerpt_bounded_full_input_untouched(self):
        packet={'provider':'test','records':[{'date':i,'details':'x'*2000} for i in range(1000)]}
        excerpt=evidence_excerpt(packet)
        self.assertLess(len(json.dumps(excerpt)),16500)
        self.assertEqual(len(packet['records']),1000)
        self.assertIn('excerpt_notice',excerpt)

    def test_all_sources_failed_no_model_call(self):
        self.app.provider=object()
        self.app.source_state={'yahoo':{'symbol':'AAPL'}}
        with patch.object(self.app.sources,'fetch',side_effect=RuntimeError('offline')),patch('hyperpass.server.Engine') as engine:
            status,result=self.call('/api/runs',{'question':'AAPL','providers':['yahoo'],'web_search':False})
            self.assertEqual(status,202)
            for _ in range(100):
                if not self.app.active: break
                time.sleep(.02)
            run=self.app.store.get(result['id'])
            self.assertEqual(run['status'],'blocked')
            self.assertEqual(run['progress']['stage'],'blocked')
            self.assertEqual(run['progress']['percent'],2)
            self.assertEqual(run['events'][-1]['progress'],run['progress'])
            self.assertFalse(run['report_complete'])
            self.assertEqual(run['reason'],run['report'])
            engine.assert_not_called()

    def test_server_exceptions_preserve_progress_and_mark_failed(self):
        from hyperpass.engine import ProviderError
        self.app.provider=object()
        for failure in (ProviderError('모델 응답 오류'),RuntimeError('private-failure-sentinel')):
            with self.subTest(error=type(failure).__name__),patch('hyperpass.server.Engine') as engine:
                def fail(*args,**kwargs):
                    emit=engine.call_args.args[1]
                    emit({'type':'progress','progress':{'percent':74,'stage':'assessing',
                        'label':'검수 중','calls_completed':4,'call_limit':12,'current_role':'head-manager'}})
                    raise failure
                engine.return_value.run.side_effect=fail
                status,result=self.call('/api/runs',{'question':'test','evidence':'provided data','web_search':False})
                self.assertEqual(status,202)
                for _ in range(100):
                    if not self.app.active: break
                    time.sleep(.02)
                run=self.app.store.get(result['id'])
                self.assertEqual(run['status'],'failed')
                self.assertEqual(run['progress']['stage'],'failed')
                self.assertEqual(run['progress']['percent'],74)
                self.assertEqual(run['progress']['calls_completed'],4)
                self.assertEqual(run['events'][-1]['progress'],run['progress'])
                self.assertFalse(run['report_complete'])
                self.assertNotIn('private-failure-sentinel',json.dumps(run))

    def test_cancellation_after_data_collection_keeps_progress_without_model_call(self):
        self.app.provider=object()
        self.app.source_state={'yahoo':{'symbol':'AAPL'}}
        def cancel_fetch(*args):
            self.app.stop_event.set()
            return {'provider':'yahoo','symbol':'AAPL','records':[{'close':123}]}
        with patch.object(self.app.sources,'fetch',side_effect=cancel_fetch):
            status,result=self.call('/api/runs',{'question':'AAPL','providers':['yahoo'],'web_search':False})
            self.assertEqual(status,202)
            for _ in range(100):
                if not self.app.active: break
                time.sleep(.02)
        run=self.app.store.get(result['id'])
        self.assertEqual(run['status'],'cancelled')
        self.assertEqual(run['progress']['stage'],'cancelled')
        self.assertEqual(run['progress']['percent'],2)
        self.assertEqual(run['usage']['calls'],0)
        self.assertFalse(run['report_complete'])
        percentages=[event['progress']['percent'] for event in run['events'] if 'progress' in event]
        self.assertEqual(percentages,sorted(percentages))
        self.assertEqual(run['events'][-1]['progress'],run['progress'])

    def test_model_discovery_does_not_connect_or_persist_key(self):
        key='sk-private-discovery-only'
        with patch('hyperpass.server.list_models',return_value=[{'id':'gpt-5-mini','name':'GPT'}]) as lookup:
            status,data=self.call('/api/ai/openai/models',{'api_key':key})
        self.assertEqual(status,200)
        self.assertEqual(lookup.call_args[0],('openai',key))
        self.assertEqual(data['models'][0]['id'],'gpt-5-mini')
        self.assertFalse(self.app.status()['connected'])
        self.assertNotIn(key,json.dumps(self.call('/api/ai')))
        for file in Path(self.temp.name).rglob('*'):
            if file.is_file(): self.assertNotIn(key.encode(),file.read_bytes())

    def test_provider_connections_independent_and_discovery_safe(self):
        with patch('hyperpass.server.OpenAIProvider') as openai,patch('hyperpass.server.make_provider') as factory:
            openai.return_value.model='gpt-5-mini'
            factory.return_value.model='claude-sonnet-4-6'
            self.assertEqual(self.call('/api/connect',{'provider':'openai','api_key':'sk-key-test-openai','model':'gpt-5-mini'})[0],200)
            self.assertEqual(self.call('/api/connect',{'provider':'anthropic','api_key':'sk-key-test-anthropic','model':'claude-sonnet-4-6'})[0],200)
        connected={x['id']:x['connected'] for x in self.call('/api/ai')[1]['providers']}
        self.assertEqual(connected,{'openai':True,'anthropic':True,'gemini':False})
        self.assertEqual(self.call('/api/disconnect',{'provider':'anthropic'})[0],200)
        self.assertTrue(self.app.status()['connected'])
        self.assertEqual(self.call('/api/connect',{'provider':'untrusted','api_key':'sk-key-test-unknown'})[0],400)

    def test_missing_evidence_rejected_before_model_call(self):
        self.app.provider=object()
        with patch('hyperpass.server.Engine') as engine:
            status,_=self.call('/api/runs',{'question':'research','web_search':False})
            self.assertEqual(status,400)
            engine.assert_not_called()

    def test_category_and_progress_persisted_and_blocked_export_label(self):
        result=self.app.start({'question':'sample','mode':'demo','category':'stock','brief':{'target':'AAPL','market':'US','horizon':'1년','outcome':'사업 전망'}})
        for _ in range(100):
            if not self.app.active: break
            time.sleep(.02)
        run=self.app.store.get(result['id'])
        self.assertEqual(run['category'],'stock')
        self.assertEqual(run['progress']['percent'],100)
        self.assertTrue(run['report_complete'])
        run.update(status='blocked',report_complete=False)
        self.app.store.put(run)
        with urlopen(self.url+'/api/runs/'+run['id']+'/export') as response:
            self.assertIn('intermediate',response.headers['Content-Disposition'])
            self.assertIn('최종 보고서 미완성',response.read().decode())

if __name__=='__main__': unittest.main()
