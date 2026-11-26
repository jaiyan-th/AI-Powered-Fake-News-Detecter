"""In-memory sliding-window rate limiter for API protection."""

import threading
import time
from collections import deque
from typing import Dict, Tuple
from fastapi import Request


class SlidingWindowRateLimiter:
    """Thread-safe per-key sliding-window rate limiter with bounded memory."""

    def __init__(self, max_keys: int = 10000):
        self._buckets: Dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds) for the given key."""
        if limit <= 0:
            return True, 0

        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            if len(self._buckets) >= self._max_keys and key not in self._buckets:
                self._prune_expired(cutoff)

            bucket = self._buckets.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])) + 1)
                return False, retry_after

            bucket.append(now)
            return True, 0

    def clear(self) -> None:
        """Reset all rate-limit buckets."""
        with self._lock:
            self._buckets.clear()

    def _prune_expired(self, cutoff: float) -> None:
        stale = [k for k, q in self._buckets.items() if not q or q[-1] <= cutoff]
        for k in stale:
            del self._buckets[k]
        if len(self._buckets) >= self._max_keys:
            self._buckets.clear()


def client_ip_from_request(request: Request, trust_proxy: bool = False) -> str:
    """Extract client IP address, optionally honoring X-Forwarded-For behind a trusted proxy."""
    if trust_proxy:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            first_ip = forwarded_for.split(",", 1)[0].strip()
            if first_ip:
                return first_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
