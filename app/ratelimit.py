"""In-memory sliding-window rate limiter.

Good enough for a single-process deployment (the default here) and dependency-free. State is per
process, so with N workers the effective limit is N times higher; put Redis behind ``RateLimiter.hit``
if you scale out. Memory is bounded: idle keys are pruned and the table has a hard ceiling.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request

from .config import get_settings


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, max_keys: int = 20_000) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float = 60.0) -> tuple[bool, float]:
        """Record a request. Returns (allowed, seconds_until_a_slot_frees_up)."""
        now = self._clock()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self._max_keys:
                    self._prune(now, window)
                q = self._hits[key] = deque()
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return False, max(0.0, window - (now - q[0]))
            q.append(now)
            return True, 0.0

    def _prune(self, now: float, window: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or now - q[-1] >= window]:
            del self._hits[key]
        if len(self._hits) >= self._max_keys:  # still full of live keys: shed the oldest half
            for key in sorted(self._hits, key=lambda k: self._hits[k][-1])[: self._max_keys // 2]:
                del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request, trusted_hops: int) -> str:
    """The caller's address. Only trusts X-Forwarded-For entries appended by our own proxies.

    The right-most ``trusted_hops`` entries were added by infrastructure we control; anything to the
    left can be forged by the client, so it is ignored.
    """
    if trusted_hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= trusted_hops:
            return parts[-trusted_hops]
    return request.client.host if request.client else "unknown"


def limit(bucket: str, setting: str):
    """FastAPI dependency factory: ``Depends(limit("explain", "explain_rate_limit_per_min"))``."""

    async def dependency(request: Request) -> None:
        settings = get_settings()
        per_min = getattr(settings, setting)
        if per_min <= 0:
            return
        limiter: RateLimiter = request.app.state.limiter
        ok, retry_after = limiter.hit(f"{bucket}:{client_ip(request, settings.trusted_proxy_hops)}", per_min)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
            )

    return dependency


limit_general = limit("api", "rate_limit_per_min")
limit_heavy = limit("heavy", "heavy_rate_limit_per_min")
limit_explain = limit("explain", "explain_rate_limit_per_min")
