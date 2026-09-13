"""Reentrant process lock backed by an OS lock for private-memory mutations."""
import os
import threading
import time


class WorkspaceLock:
    def __init__(self):
        self.thread_lock = threading.RLock()
        self.local = threading.local()

    def __enter__(self):
        from app.config import settings
        self.thread_lock.acquire()
        depth = getattr(self.local, "depth", 0)
        if depth:
            self.local.depth = depth + 1
            return self
        handle = None
        try:
            root = settings.artifact_root.resolve()
            root.mkdir(parents=True, exist_ok=True)
            handle = (root / ".personal-memory.lock").open("a+b")
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            deadline = time.monotonic() + 30
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("个人数据正在被另一个进程更新，请稍后重试")
                    time.sleep(.05)
            self.local.handle = handle
            self.local.depth = 1
            return self
        except BaseException:
            if handle:
                handle.close()
            self.thread_lock.release()
            raise

    def __exit__(self, *_):
        self.local.depth -= 1
        try:
            if self.local.depth == 0:
                handle = self.local.handle
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()
        finally:
            self.thread_lock.release()
