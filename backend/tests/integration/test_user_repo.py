import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_get_by_username_returns_seeded_user(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.auth.user_repo import get_by_username
    from app.storage.pg import dispose_engine, get_sessionmaker
    from scripts.seed_users import seed

    try:
        await seed()
        async with get_sessionmaker()() as session:
            user = await get_by_username(session, "admin")
        assert user is not None
        assert user.username == "admin"
        assert user.role == "admin"
        assert user.permission_level == "L3"
        assert user.is_active is True
    finally:
        await dispose_engine()


@pytest.mark.asyncio
async def test_get_by_username_returns_none_on_missing(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.auth.user_repo import get_by_username
    from app.storage.pg import dispose_engine, get_sessionmaker

    try:
        async with get_sessionmaker()() as session:
            user = await get_by_username(session, "nonexistent_user")
        assert user is None
    finally:
        await dispose_engine()


@pytest.mark.asyncio
async def test_touch_last_login_updates_timestamp(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.auth.user_repo import get_by_username, touch_last_login
    from app.storage.pg import dispose_engine, get_sessionmaker
    from scripts.seed_users import seed

    try:
        await seed()
        async with get_sessionmaker()() as session:
            user = await get_by_username(session, "admin")
            assert user is not None
            before = user.last_login_at
            await touch_last_login(session, user_id=user.user_id)
            await session.commit()

            reloaded = await get_by_username(session, "admin")
            assert reloaded is not None
            assert reloaded.last_login_at is not None
            if before is not None:
                assert reloaded.last_login_at >= before
    finally:
        await dispose_engine()
