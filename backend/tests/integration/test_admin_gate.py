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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
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


async def _token(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_admin_ping_admin_200(client):
    tok = await _token(client, "admin", "Admin@123456")
    r = await client.get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["pong"] is True


@pytest.mark.asyncio
async def test_admin_ping_employee_403(client):
    tok = await _token(client, "employee_demo", "Employee@12345")
    r = await client.get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert r.json()["code"] == 40301


@pytest.mark.asyncio
async def test_admin_ping_guest_403(client):
    tok = await _token(client, "guest_demo", "Guest@123456")
    r = await client.get("/api/v1/admin/ping", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert r.json()["code"] == 40301


@pytest.mark.asyncio
async def test_admin_ping_no_token_401(client):
    r = await client.get("/api/v1/admin/ping")
    assert r.status_code == 401
    assert r.json()["code"] == 40101


@pytest.mark.asyncio
async def test_whoami_allows_all_three_roles(client):
    for username, password, expected_role, expected_pl in [
        ("admin", "Admin@123456", "admin", "L3"),
        ("employee_demo", "Employee@12345", "employee", "L2"),
        ("guest_demo", "Guest@123456", "guest", "L1"),
    ]:
        tok = await _token(client, username, password)
        r = await client.get(
            "/api/v1/admin/whoami",
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, f"{username}: {r.text}"
        body = r.json()
        assert body["role"] == expected_role
        assert body["pl"] == expected_pl
