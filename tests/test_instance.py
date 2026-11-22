import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hyperpass.instance import InstanceInUse, InstanceLock


class InstanceTests(unittest.TestCase):
    def test_exclusive_lock_reports_existing_port_without_changing_research(self):
        with tempfile.TemporaryDirectory() as folder:
            record=Path(folder)/'research.sqlite3'
            record.write_bytes(b'existing research sentinel')
            first=InstanceLock(folder).acquire()
            try:
                first.set_port(8771)
                with self.assertRaises(InstanceInUse) as caught:
                    InstanceLock(folder).acquire()
                self.assertEqual(caught.exception.url,'http://127.0.0.1:8771')
                self.assertEqual(record.read_bytes(),b'existing research sentinel')
            finally:
                first.release()
            retry=InstanceLock(folder).acquire()
            retry.release()

    def test_independent_data_directories_can_run_concurrently(self):
        with tempfile.TemporaryDirectory() as folder:
            first=InstanceLock(Path(folder)/'one').acquire()
            second=InstanceLock(Path(folder)/'two').acquire()
            first.release()
            second.release()

    def test_crashed_subprocess_does_not_leave_a_stale_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            script=('import os,sys; from hyperpass.instance import InstanceLock; '
                    'lock=InstanceLock(sys.argv[1]).acquire(); lock.set_port(8770); os._exit(17)')
            result=subprocess.run([sys.executable,'-c',script,folder],capture_output=True,timeout=10,
                                  cwd=Path(__file__).resolve().parents[1],
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.assertEqual(result.returncode,17,result.stderr.decode(errors='replace'))
            retry=InstanceLock(folder).acquire()
            retry.release()


if __name__=='__main__':
    unittest.main()
