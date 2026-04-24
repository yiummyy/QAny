from typing import Any

from redis.asyncio import Redis, from_url

from app.config import get_settings

_client: Redis[Any] | None = None


def get_redis() -> Redis[Any]:
    global _client
    if _client is None:
        settings = get_settings()
        _client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
