"""Per-IP rate limiting for the login and signup endpoints.

Attempts are counted in this process's memory, which fits a single app
instance (the Railway setup). With several instances each would allow the full
limit on its own; that would need a shared store such as Redis.
"""

import math
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from .config import settings

WINDOW_SECONDS = 60.0


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def hit(self, key: tuple[str, str], limit: int, now: float | None = None) -> float | None:
        """Record an attempt for `key`.

        Returns None if it's allowed, or the seconds until the next attempt
        would be. Refused attempts aren't recorded, so waiting out the window
        always works.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            self._sweep(now)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                return hits[0] + WINDOW_SECONDS - now
            hits.append(now)
            return None

    def _sweep(self, now: float) -> None:
        # Drop idle keys about once a window, so memory doesn't grow with
        # every IP address ever seen.
        if now - self._last_sweep < WINDOW_SECONDS:
            return
        self._last_sweep = now
        cutoff = now - WINDOW_SECONDS
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    hops = settings.trusted_proxy_count
    if hops > 0:
        # Each trusted proxy appends the address it received the request from,
        # so the entry `hops` from the end is the one the outermost proxy saw.
        # Anything before it came from the client and can be forged.
        forwarded = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops]
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str):
    """Dependency allowing AUTH_RATE_LIMIT_PER_MINUTE requests per IP per minute."""

    def dependency(request: Request) -> None:
        limit = settings.auth_rate_limit_per_minute
        if limit <= 0:
            return
        retry_after = limiter.hit((scope, client_ip(request)), limit)
        if retry_after is not None:
            seconds = max(1, math.ceil(retry_after))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Please wait {seconds} seconds and try again.",
                headers={"Retry-After": str(seconds)},
            )

    return dependency
