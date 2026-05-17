"""Rate limiting — user daily quota + concurrency + IP rate limit (B8)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.auth.claims import UserClaims

logger = logging.getLogger(__name__)

DEFAULT_DAILY_QUOTA = 200
_IP_BUCKETS: dict[str, tuple[float, int]] = {}  # ip → (window_start, count)
_IP_RATE_LIMIT = 3  # requests per second
_IP_WINDOW = 1.0  # seconds


async def check_user_daily_quota(user_id: str) -> None:
    """Raise HTTP 429 if user has exceeded their daily quota."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"user:quota:daily:{user_id}:{today}"

    try:
        from app.storage.redis_client import get_redis

        redis = get_redis()
        count = await redis.get(key)
        current = int(count) if count else 0

        if current >= DEFAULT_DAILY_QUOTA:
            raise HTTPException(
                status_code=429,
                detail={"code": 42901, "message": f"您今日问答次数已用完 ({DEFAULT_DAILY_QUOTA}次/天)"},
            )

        # Increment and set TTL (best-effort, non-blocking)
        await redis.incr(key)
        await redis.expire(key, 86400 * 2)
    except HTTPException:
        raise
    except Exception:
        # Redis unavailable — allow pass (fail open)
        pass


async def check_user_concurrency(user_id: str) -> str | None:
    """Acquire a concurrency slot. Returns a cleanup token, or raises HTTP 429."""
    key = f"user:active:{user_id}"
    token = f"{user_id}:{time.monotonic()}"

    try:
        from app.storage.redis_client import get_redis

        redis = get_redis()
        # SET NX — only one active connection per user
        acquired = await redis.set(key, token, nx=True, ex=300)  # 5 min TTL

        if not acquired:
            raise HTTPException(
                status_code=429,
                detail={"code": 42902, "message": "您有一个正在进行的问答会话，请等待完成"},
            )

        return token
    except HTTPException:
        raise
    except Exception:
        return None  # Redis unavailable — allow pass


async def release_user_concurrency(user_id: str, token: str | None) -> None:
    """Release the concurrency slot."""
    if not token:
        return
    try:
        from app.storage.redis_client import get_redis

        redis = get_redis()
        key = f"user:active:{user_id}"
        # Only release if the token matches (prevent accidentally releasing another connection)
        current = await redis.get(key)
        if current and (current.decode() if isinstance(current, bytes) else current) == token:
            await redis.delete(key)
    except Exception:
        pass


def check_ip_rate_limit(request: Request) -> None:
    """Raise HTTP 429 if IP exceeds rate limit (3 req/s, in-process bucket)."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()

    bucket = _IP_BUCKETS.get(client_ip)
    if bucket is None:
        _IP_BUCKETS[client_ip] = (now, 1)
        return

    window_start, count = bucket
    if now - window_start > _IP_WINDOW:
        # New window
        _IP_BUCKETS[client_ip] = (now, 1)
        return

    if count >= _IP_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail={"code": 42903, "message": "请求过于频繁，请稍后重试"},
            headers={"Retry-After": "1"},
        )

    _IP_BUCKETS[client_ip] = (window_start, count + 1)

    # Periodic cleanup of stale entries (every 100 requests)
    if sum(1 for _ in _IP_BUCKETS) > 1000:
        stale = [ip for ip, (ws, _) in _IP_BUCKETS.items() if now - ws > _IP_WINDOW * 10]
        for ip in stale:
            del _IP_BUCKETS[ip]
