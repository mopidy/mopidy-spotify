import threading


class ThreadJoiner:
    def __init__(self, timeout: int = 1):
        self.timeout = timeout

    def __enter__(self):
        self.before = set(threading.enumerate())

    def __exit__(self, exc_type, exc_val, exc_tb):
        new_threads = set(threading.enumerate()) - self.before
        for thread in new_threads:
            thread.join(timeout=self.timeout)
            if thread.is_alive():
                msg = f"Timeout joining thread {thread}"
                raise RuntimeError(msg)
