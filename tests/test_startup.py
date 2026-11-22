import errno
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from hyperpass.server import main
from hyperpass.instance import InstanceLock


class StartupTests(unittest.TestCase):
    def invoke(self, arguments, outcomes):
        output=io.StringIO()
        app=Mock()
        with tempfile.TemporaryDirectory() as folder, \
             patch('sys.argv',['app.py','--no-browser',*arguments]), \
             patch('hyperpass.server.default_data_dir',return_value=Path(folder)), \
             patch('hyperpass.server.Application',return_value=app), \
             patch('hyperpass.server.serve',side_effect=outcomes) as serve, \
             patch('sys.stdout',output):
            code=main()
        return code,output.getvalue(),serve,app

    def test_automatic_start_uses_first_available_port_and_prints_its_url(self):
        for occupied in (OSError(errno.EADDRINUSE,'occupied'),OSError(10048,'occupied')):
            with self.subTest(error=occupied.errno):
                server=Mock(server_port=8766)
                code,output,serve,app=self.invoke([], [occupied,server])
                self.assertEqual(code,0)
                self.assertEqual([call.args[1] for call in serve.call_args_list],[8765,8766])
                self.assertIn('http://127.0.0.1:8766',output)
                server.serve_forever.assert_called_once()
                server.server_close.assert_called_once()
                app.stop_event.set.assert_called_once()

    def test_explicit_port_stays_fixed_on_success(self):
        server=Mock(server_port=9123)
        code,output,serve,_=self.invoke(['--port','9123'],[server])
        self.assertEqual(code,0)
        self.assertEqual([call.args[1] for call in serve.call_args_list],[9123])
        self.assertIn('http://127.0.0.1:9123',output)

    def test_explicit_occupied_port_does_not_fall_back(self):
        code,output,serve,_=self.invoke(['--port','9123'],[OSError(errno.EADDRINUSE,'occupied')])
        self.assertEqual(code,1)
        self.assertEqual(serve.call_count,1)
        self.assertIn('지정한 포트 9123',output)
        self.assertIn('--port를 생략',output)

    def test_permission_error_is_reported_without_trying_other_ports(self):
        code,output,serve,_=self.invoke([],[OSError(errno.EACCES,'permission denied')])
        self.assertEqual(code,1)
        self.assertEqual(serve.call_count,1)
        self.assertIn('접근 권한',output)
        self.assertIn(f'OS 오류 {errno.EACCES}',output)
        self.assertNotIn('모두 사용 중',output)

    def test_automatic_port_search_is_bounded_to_twenty_ports(self):
        code,output,serve,_=self.invoke([],[OSError(errno.EADDRINUSE,'occupied') for _ in range(20)])
        self.assertEqual(code,1)
        self.assertEqual([call.args[1] for call in serve.call_args_list],list(range(8765,8785)))
        self.assertIn('8765~8784가 모두 사용 중',output)

    def test_existing_instance_prevents_application_and_store_initialization(self):
        with tempfile.TemporaryDirectory() as folder:
            lock=InstanceLock(folder).acquire()
            lock.set_port(8772)
            try:
                output=io.StringIO()
                with patch('sys.argv',['app.py','--no-browser','--data-dir',folder]), \
                     patch('hyperpass.server.Application') as application, \
                     patch('hyperpass.server.serve') as serve, patch('sys.stdout',output):
                    self.assertEqual(main(),0)
                application.assert_not_called()
                serve.assert_not_called()
                self.assertIn('기존 앱: http://127.0.0.1:8772',output.getvalue())
            finally:
                lock.release()

    def test_application_failure_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('sys.argv',['app.py','--no-browser','--data-dir',folder]), \
                 patch('hyperpass.server.Application',side_effect=ValueError('startup failure')):
                with self.assertRaisesRegex(ValueError,'startup failure'):
                    main()
            retry=InstanceLock(folder).acquire()
            retry.release()


if __name__=='__main__':
    unittest.main()
