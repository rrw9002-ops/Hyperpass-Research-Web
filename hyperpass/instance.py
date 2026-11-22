"""One process per research data directory; OS locks release after a crash."""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path


class InstanceInUse(RuntimeError):
    def __init__(self, url=None):
        super().__init__('This research data directory is already open.')
        self.url=url


class InstanceLock:
    def __init__(self, folder):
        self.folder=Path(folder).resolve()
        self.handle=None

    @staticmethod
    def _existing_url(handle):
        try:
            handle.seek(1)
            data=json.loads(handle.read(256).decode('utf-8'))
            port=data.get('port')
            if type(port) is int and 1<=port<=65535:
                return f'http://127.0.0.1:{port}'
        except (OSError,ValueError,AttributeError,UnicodeError):
            pass
        return None

    def acquire(self):
        if self.handle is not None:
            raise RuntimeError('Instance lock is already acquired.')
        self.folder.mkdir(parents=True,exist_ok=True)
        descriptor=os.open(self.folder/'.instance.lock',os.O_RDWR|os.O_CREAT,0o600)
        handle=os.fdopen(descriptor,'r+b',buffering=0)
        try:
            # Windows byte-range locking needs a stable first byte. Never unlink
            # the file: different inodes could allow two processes to hold locks.
            if os.fstat(handle.fileno()).st_size==0:
                handle.write(b'\0')
            handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EACCES,errno.EAGAIN,errno.EDEADLK) or getattr(exc,'winerror',None) in (32,33):
                    raise InstanceInUse(self._existing_url(handle)) from None
                raise
            self.handle=handle
            self.handle.seek(1)
            self.handle.write(b'{}')
            self.handle.truncate()
            return self
        except BaseException:
            if self.handle is handle:
                self.release()
            else:
                handle.close()
            raise

    def set_port(self, port):
        if self.handle is None:
            raise RuntimeError('Instance lock is not acquired.')
        if type(port) is not int or not 1<=port<=65535:
            raise ValueError('Invalid local server port.')
        self.handle.seek(1)
        self.handle.write(json.dumps({'port':port},separators=(',',':')).encode('ascii'))
        self.handle.truncate()

    def release(self):
        handle,self.handle=self.handle,None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        finally:
            handle.close()
