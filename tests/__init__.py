import threading
from types import TracebackType


class ThreadJoiner:
    def __init__(self, timeout: int = 1):
        self.timeout = timeout

    def __enter__(self):
        self.before = set(threading.enumerate())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        new_threads = set(threading.enumerate()) - self.before
        for thread in new_threads:
            thread.join(timeout=self.timeout)
            if thread.is_alive():
                msg = f"Timeout joining thread {thread}"
                raise RuntimeError(msg)
