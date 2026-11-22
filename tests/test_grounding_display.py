import threading
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from hyperpass.server import Application, serve


class GroundingDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(self.temp.name)
        self.server = serve(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.run_id = 'a' * 32
        self.path = f'/api/runs/{self.run_id}/artifacts/news-analyst-v1/search-suggestions'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def save(self, html):
        self.app.store.put({'id': self.run_id, 'status': 'completed', 'artifacts': [
            {'id': 'news-analyst-v1', 'search_suggestions_html': html}]})

    def request(self, path=None, headers=None):
        try:
            response = urlopen(Request(self.base + (path or self.path), headers=headers or {}), timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_stored_html_is_served_in_strict_sandbox(self):
        html = '<style>a{color:blue}</style><a href="https://www.google.com/search?q=test" target="_blank">Search</a><script>alert(1)</script>'
        self.save(html)
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(body.decode(), html)
        self.assertEqual(headers['Content-Type'], 'text/html; charset=utf-8')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        policy = headers['Content-Security-Policy']
        for directive in ("default-src 'none'", "script-src 'none'", "style-src 'unsafe-inline'",
                          "img-src data:", "form-action 'none'", "base-uri 'none'",
                          "frame-ancestors 'self'", 'sandbox allow-popups allow-popups-to-escape-sandbox'):
            self.assertIn(directive, policy)
        self.assertNotIn('allow-scripts', policy)
        self.assertNotIn('allow-same-origin', policy)

    def test_missing_oversized_and_invalid_records_are_not_served(self):
        self.assertEqual(self.request()[0], 404)
        for invalid in ('', {'html': 'bad'}, '가' * 70000):
            self.save(invalid)
            self.assertEqual(self.request()[0], 404)
        self.save('<div>OK</div>')
        self.assertEqual(self.request(self.path.replace('news-analyst-v1', 'other-v1'))[0], 404)
        self.assertEqual(self.request(self.path.replace('news-analyst-v1', '..%2f..%2fapp.py'))[0], 404)
        self.assertEqual(self.request(self.path.replace(self.run_id, 'b' * 32))[0], 404)

    def test_host_and_origin_restrictions_apply_to_html(self):
        self.save('<div>OK</div>')
        self.assertEqual(self.request(headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request(headers={'Origin': 'https://evil.example'})[0], 403)

    def test_main_document_keeps_original_policy(self):
        status, headers, _ = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('unsafe-inline', headers['Content-Security-Policy'])


if __name__ == '__main__':
    unittest.main()
