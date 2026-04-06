from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import time


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def evaluate(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        normalized_limit = max(1, int(limit))
        normalized_window = max(1, int(window_seconds))
        now = time()

        with self._lock:
            bucket = self._requests[key]
            while bucket and now - bucket[0] >= normalized_window:
                bucket.popleft()

            if len(bucket) >= normalized_limit:
                retry_after = max(1, int(normalized_window - (now - bucket[0])))
                return RateLimitDecision(
                    allowed=False,
                    limit=normalized_limit,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )

            bucket.append(now)
            remaining = max(0, normalized_limit - len(bucket))
            return RateLimitDecision(
                allowed=True,
                limit=normalized_limit,
                remaining=remaining,
                retry_after_seconds=0,
            )

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        return self.evaluate(key, limit, window_seconds).allowed

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


rate_limiter = RateLimiter()
