import pytest

from app.storage.redis_client import close_redis, get_redis

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_redis_ping(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.config import get_settings

    get_settings.cache_clear()
    await close_redis()  # ensure fresh client picks up env
    r = get_redis()
    assert await r.ping() is True
    await close_redis()


@pytest.mark.asyncio
async def test_redis_setex_and_get(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.config import get_settings

    get_settings.cache_clear()
    await close_redis()
    r = get_redis()
    await r.setex("k1", 10, "v1")
    assert await r.get("k1") == "v1"
    await close_redis()
