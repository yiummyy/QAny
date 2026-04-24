"""Per-username login failure rate limiter — Spec §5.6 (5 fails / 10min)."""

from __future__ import annotations

from app.storage.redis_client import get_redis

_KEY_PREFIX = "ratelimit:login"
_WINDOW_SECONDS = 600  # 10 minutes
_THRESHOLD = 5


class LoginBlocked(Exception):
    """Raised when a username has exceeded the failure threshold.

    The caller (API layer) should translate this into HTTP 429 + code 42900,
    including retry_after in the response headers.
    """

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"login blocked, retry after {retry_after}s")
        self.retry_after = retry_after


def _key(username: str) -> str:
    return f"{_KEY_PREFIX}:{username}"


async def record_failure(username: str) -> int:
    """Increment failure counter and refresh TTL. Returns current count."""
    r = get_redis()
    key = _key(username)
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _WINDOW_SECONDS)
    count, _ = await pipe.execute()
    return int(count)


async def ensure_not_blocked(username: str) -> None:
    """Raise LoginBlocked if the username has reached the failure threshold."""
    r = get_redis()
    key = _key(username)
    count_raw = await r.get(key)
    if count_raw is None:
        return
    if int(count_raw) >= _THRESHOLD:
        ttl = await r.ttl(key)
        raise LoginBlocked(retry_after=max(ttl, 1))


async def reset(username: str) -> None:
    """Clear failure counter — call after a successful login."""
    await get_redis().delete(_key(username))
