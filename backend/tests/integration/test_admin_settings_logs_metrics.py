"""Integration tests for Admin settings / logs / metrics endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(pg_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("ENVIRONMENT", "test")

    from app.config import get_settings
    get_settings.cache_clear()

    from scripts.seed_users import seed
    await seed()

    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        yield c


@pytest.fixture
async def admin_headers(client):
    resp = await client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
async def employee_headers(client):
    resp = await client.post("/api/v1/auth/login", json={
        "username": "employee_demo",
        "password": "employee123",
    })
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_as_admin(client, admin_headers):
    resp = await client.get("/api/v1/admin/settings", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "config" in body
    assert "updated_at" in body
    assert "rerank_enabled" in body["config"]


@pytest.mark.asyncio
async def test_get_settings_as_employee_denied(client, employee_headers):
    resp = await client.get("/api/v1/admin/settings", headers=employee_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_settings_optimistic_lock(client, admin_headers):
    # Read current
    resp = await client.get("/api/v1/admin/settings", headers=admin_headers)
    current = resp.json()

    # Update with correct updated_at
    resp = await client.put(
        "/api/v1/admin/settings",
        json={"config": current["config"], "updated_at": current["updated_at"]},
        headers=admin_headers,
    )
    assert resp.status_code == 200

    # Attempt update with stale updated_at — should conflict
    resp = await client.put(
        "/api/v1/admin/settings",
        json={"config": current["config"], "updated_at": current["updated_at"]},
        headers=admin_headers,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_logs_empty(client, admin_headers):
    resp = await client.get("/api/v1/admin/logs", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert "items" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_list_logs_with_filters(client, admin_headers):
    resp = await client.get(
        "/api/v1/admin/logs",
        params={"limit": 5, "offset": 0, "status_filter": "success"},
        headers=admin_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_logs_as_employee_denied(client, employee_headers):
    resp = await client.get("/api/v1/admin/logs", headers=employee_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metrics(client, admin_headers):
    resp = await client.get("/api/v1/admin/metrics", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "today_questions" in body
    assert "success_rate" in body
    assert "avg_response_ms" in body
    assert "today_cost_rmb" in body
    assert "feedback_thumbs_up" in body
    assert "feedback_thumbs_down" in body
    # All values should be numbers
    for k in body:
        assert isinstance(body[k], (int, float))


@pytest.mark.asyncio
async def test_get_metrics_as_employee_denied(client, employee_headers):
    resp = await client.get("/api/v1/admin/metrics", headers=employee_headers)
    assert resp.status_code == 403
