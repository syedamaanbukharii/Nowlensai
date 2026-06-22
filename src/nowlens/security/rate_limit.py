"""Rate limiting.

A sliding-window limiter keyed by identity (user id or client IP). It uses Redis
when a client is available (so limits hold across processes) and falls back to an
in-process window otherwise. The in-memory path is fully deterministic and
unit-tested; the Redis path uses a sorted set of request timestamps.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from nowlens.core.config import SecuritySettings
from nowlens.core.logging import get_logger

log = get_logger(__name__)

_WINDOW_SECONDS = 60.0


@dataclass(slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after: float


class RateLimiter:
    """Sliding-window limiter.

    ``limit`` requests are allowed per 60s window, plus a one-off ``burst``
    allowance. Pass a redis asyncio client to share state across workers.
    """

    def __init__(
        self,
        *,
        limit: int,
        burst: int = 0,
        redis: Any = None,  # redis.asyncio.Redis | None
        namespace: str = "nowlens:rl",
    ) -> None:
        self._limit = limit + burst
        self._redis = redis
        self._namespace = namespace
        self._local: dict[str, deque[float]] = defaultdict(deque)

    @classmethod
    def from_settings(cls, settings: SecuritySettings, *, redis: Any = None) -> RateLimiter:
        return cls(
            limit=settings.rate_limit_per_minute, burst=settings.rate_limit_burst, redis=redis
        )

    async def check(self, identity: str) -> RateLimitDecision:
        now = time.time()
        if self._redis is not None:
            return await self._check_redis(identity, now)
        return self._check_local(identity, now)

    # -- in-memory ---------------------------------------------------------

    def _check_local(self, identity: str, now: float) -> RateLimitDecision:
        window = self._local[identity]
        cutoff = now - _WINDOW_SECONDS
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self._limit:
            retry_after = max(0.0, window[0] + _WINDOW_SECONDS - now)
            return RateLimitDecision(False, 0, round(retry_after, 2))
        window.append(now)
        return RateLimitDecision(True, self._limit - len(window), 0.0)

    # -- redis -------------------------------------------------------------

    async def _check_redis(self, identity: str, now: float) -> RateLimitDecision:
        key = f"{self._namespace}:{identity}"
        cutoff = now - _WINDOW_SECONDS
        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zadd(key, {f"{now}": now})
            pipe.zcard(key)
            pipe.expire(key, int(_WINDOW_SECONDS) + 1)
            _, _, count, _ = await pipe.execute()
        except Exception as exc:  # noqa: BLE001 - never fail open silently without a log
            log.warning("ratelimit.redis_unavailable", error=str(exc))
            return self._check_local(identity, now)

        if count > self._limit:
            return RateLimitDecision(False, 0, round(_WINDOW_SECONDS, 2))
        return RateLimitDecision(True, max(0, self._limit - int(count)), 0.0)
