import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_revoke_then_is_revoked_returns_true(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import is_revoked, revoke
    from app.storage.redis_client import close_redis

    try:
        await revoke(jti="j_abc", ttl_seconds=60)
        assert await is_revoked("j_abc") is True
        assert await is_revoked("j_not_there") is False
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_revoke_honors_ttl(redis_url, monkeypatch):
    import asyncio

    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import is_revoked, revoke
    from app.storage.redis_client import close_redis

    try:
        await revoke(jti="j_short", ttl_seconds=1)
        assert await is_revoked("j_short") is True
        await asyncio.sleep(1.5)
        assert await is_revoked("j_short") is False
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_revoke_clamps_non_positive_ttl(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import is_revoked, revoke
    from app.storage.redis_client import close_redis

    try:
        await revoke(jti="j_already_expired", ttl_seconds=0)
        assert await is_revoked("j_already_expired") is False
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_register_pair_and_pop_pair_bidirectional(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import pop_pair, register_pair
    from app.storage.redis_client import close_redis

    try:
        await register_pair(access_jti="j_acc", refresh_jti="j_ref", ttl_seconds=60)
        partner = await pop_pair("j_acc")
        assert partner == "j_ref"
        assert await pop_pair("j_acc") is None
        assert await pop_pair("j_ref") is None
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_pop_pair_on_missing_returns_none(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import pop_pair
    from app.storage.redis_client import close_redis

    try:
        assert await pop_pair("never_registered") is None
    finally:
        await close_redis()


@pytest.mark.asyncio
async def test_register_pair_clamps_non_positive_ttl(redis_url, monkeypatch):
    monkeypatch.setenv("REDIS_URL", redis_url)
    from app.auth.blacklist import pop_pair, register_pair
    from app.storage.redis_client import close_redis

    try:
        await register_pair(access_jti="j_a", refresh_jti="j_b", ttl_seconds=0)
        assert await pop_pair("j_a") is None
    finally:
        await close_redis()
