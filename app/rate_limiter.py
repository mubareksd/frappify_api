from collections import defaultdict, deque
from threading import Lock
from time import time


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time()

        with self._lock:
            bucket = self._requests[key]
            while bucket and now - bucket[0] >= window_seconds:
                bucket.popleft()

            if len(bucket) >= limit:
                return False

            bucket.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


rate_limiter = RateLimiter()
