"""End-to-end auth API: login → protected access → refresh → logout → blacklisted."""

import time

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(pg_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)

    from app.config import get_settings
    get_settings.cache_clear()

    from scripts.seed_users import seed
    await seed()

    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c

    # Teardown
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET is_active=TRUE "
                "WHERE username IN ('admin','employee_demo','guest_demo')"
            )
        )
    await engine.dispose()

    from app.storage.redis_client import close_redis, get_redis

    r = get_redis()
    for uname in ("admin", "employee_demo", "guest_demo"):
        await r.delete(f"ratelimit:login:{uname}")
    for prefix in ("jwt_blacklist", "jwt_pair"):
        async for key in r.scan_iter(match=f"{prefix}:*"):
            await r.delete(key)

    from app.storage.pg import dispose_engine
    await dispose_engine()
    await close_redis()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_login_success_returns_access_and_refresh(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "Bearer"
    assert body["user"]["role"] == "admin"
    assert body["user"]["permission_level"] == "L3"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_40101(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40101


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_40101(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "not_a_user", "password": "anything"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == 40101


@pytest.mark.asyncio
async def test_login_fifth_failure_blocks_with_42900(client):
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"username": "employee_demo", "password": "wrong"},
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "employee_demo", "password": "Employee@12345"},
    )
    assert r.status_code == 429
    assert r.json()["code"] == 42900


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    refresh = r.json()["refresh_token"]

    r2 = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert r2.status_code == 200
    assert "access_token" in r2.json()


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]

    r2 = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40101


@pytest.mark.asyncio
async def test_logout_blacklists_token(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]

    r_before = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_before.status_code == 200

    r_out = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_out.status_code == 204

    r_after = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_after.status_code == 401
    assert r_after.json()["code"] == 40101


@pytest.mark.asyncio
async def test_logout_cascades_to_refresh_token(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]
    refresh = r.json()["refresh_token"]

    r_out = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_out.status_code == 204

    r_ref = await client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert r_ref.status_code == 401
    assert r_ref.json()["code"] == 40101


@pytest.mark.asyncio
async def test_logout_via_refresh_cascades_to_access(client):
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    access = r.json()["access_token"]
    refresh = r.json()["refresh_token"]

    r_out = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {refresh}"},
    )
    assert r_out.status_code == 204

    r_me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r_me.status_code == 401
    assert r_me.json()["code"] == 40101


@pytest.mark.asyncio
async def test_expired_token_rejected(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("JWT_ACCESS_TTL_SECONDS", "1")
    get_settings.cache_clear()

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin@123456"},
    )
    token = r.json()["access_token"]
    time.sleep(2)

    r2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40101

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_inactive_user_cannot_authenticate(client, pg_url):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "guest_demo", "password": "Guest@123456"},
    )
    token = r.json()["access_token"]

    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET is_active=FALSE WHERE username='guest_demo'")
        )
    await engine.dispose()

    r2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 401
    assert r2.json()["code"] == 40102
