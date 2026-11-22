import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hyperpass.server import Application, serve


class IndicatorStudioHTTPTests(unittest.TestCase):
    code = '//@version=6\nindicator("내 지표", overlay=true)\nplot(ta.sma(close, 20))'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = Application(self.root / 'data', team_dir=self.root / 'team')
        server = serve(self.app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f'http://127.0.0.1:{server.server_port}/api/indicators'

    def request(self, path='', payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=data, headers={
            'Content-Type': 'application/json', 'X-CSRF-Token': self.app.csrf})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_edit_persists_under_same_id_and_reopens(self):
        status, saved = self.request(payload={'name': '나의 이동평균', 'code': self.code})
        self.assertEqual(status, 201, saved)
        changed = {**saved, 'name': '50봉', 'code': self.code.replace('20', '50')}
        self.assertEqual(self.request(payload=changed), (200, changed))
        reopened = Application(self.root / 'data', team_dir=self.root / 'team')
        self.assertEqual(reopened.indicators.list(), [changed])
        self.assertEqual(self.request(payload={**changed, 'code': 'strategy("x")'})[0], 400)
        self.assertEqual(self.request()[1]['indicators'], [changed])

    def test_generation_uses_selected_model_and_keeps_preview_unsaved(self):
        self.app.ai_providers['openai'] = MagicMock(model='test-model', _key='fixture-value')
        body = {'prompt': '이동평균을 그려줘', 'provider': 'openai', 'model': 'gpt-5.4', 'reasoning': 'medium'}
        with patch('hyperpass.model_providers.make_provider') as create:
            engine = create.return_value
            engine.complete.return_value = {'data': {'name': '평균', 'code': self.code}}
            status, draft = self.request('/generate', body)
            self.assertEqual(status, 200, draft)
            self.assertEqual(draft['code'], self.code)
            create.assert_called_once_with('openai', 'fixture-value', 'gpt-5.4', reasoning='medium')
            engine.complete.assert_called_once()
            self.assertFalse(engine.complete.call_args.kwargs['web_search'])
            self.assertEqual(self.request()[1]['indicators'], [])
            self.assertEqual(self.app.tv_jobs.list(), [])
            engine.complete.return_value = {'data': {'name': '오류', 'code': 'strategy("x")'}}
            self.assertEqual(self.request('/generate', body)[0], 400)
        self.assertEqual(self.request('/generate', {**body, 'provider': 'gemini'})[0], 400)
