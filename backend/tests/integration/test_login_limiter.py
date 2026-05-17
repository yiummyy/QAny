import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fifth_failure_triggers_block(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.login_limiter import ensure_not_blocked, record_failure, reset
    from app.storage.redis_client import close_redis

    try:
        await reset("alice")
        for _ in range(5):
            await record_failure("alice")
        with pytest.raises(Exception) as exc:
            await ensure_not_blocked("alice")
        assert getattr(exc.value, "retry_after", None) is not None
    finally:
        await reset("alice")
        await close_redis()


@pytest.mark.asyncio
async def test_reset_on_success(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.login_limiter import ensure_not_blocked, record_failure, reset
    from app.storage.redis_client import close_redis

    try:
        await reset("bob")
        for _ in range(3):
            await record_failure("bob")
        await reset("bob")
        await ensure_not_blocked("bob")
    finally:
        await reset("bob")
        await close_redis()


@pytest.mark.asyncio
async def test_under_threshold_still_allows(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.login_limiter import ensure_not_blocked, record_failure, reset
    from app.storage.redis_client import close_redis

    try:
        await reset("carol")
        for _ in range(4):
            await record_failure("carol")
        await ensure_not_blocked("carol")
    finally:
        await reset("carol")
        await close_redis()
