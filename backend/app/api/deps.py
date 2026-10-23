"""Shared API dependencies."""

import threading
import time

from fastapi import HTTPException, Request


class RateLimiter:
    """Per-client token bucket. In-process state is enough for a single
    instance; behind several replicas this would move to Postgres or Redis."""

    def __init__(self, capacity: int, per_seconds: float) -> None:
        self.capacity = capacity
        self.rate = capacity / per_seconds
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens < 1:
                raise HTTPException(status_code=429, detail="Too many requests; slow down")
            self._buckets[key] = (tokens - 1, now)


upload_limit = RateLimiter(capacity=10, per_seconds=60)
copilot_limit = RateLimiter(capacity=20, per_seconds=60)
