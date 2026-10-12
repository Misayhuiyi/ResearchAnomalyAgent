"""One process owns a local runtime; OS releases the lease after a crash."""
import os
from pathlib import Path


class RuntimeBusy(RuntimeError): pass


class RuntimeLease:
    def __init__(self, root):
        self.root=Path(root)
        self.handle=None

    def __enter__(self):
        self.root.mkdir(parents=True,exist_ok=True)
        handle=(self.root/'.service.lock').open('a+b')
        try:
            if not handle.tell(): handle.write(b'0');handle.flush()
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise RuntimeBusy('该数据目录正在使用。请先关闭原服务，不能同时启动或执行维护。') from None
        self.handle=handle
        return self

    def __exit__(self,*args):
        if self.handle is not None:
            self.handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN)
            self.handle.close();self.handle=None
