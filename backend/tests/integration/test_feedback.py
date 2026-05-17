"""Integration tests for POST /api/v1/feedback."""

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(pg_url, redis_url, monkeypatch):
    """Create a test client with PG + Redis."""
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
async def auth_headers(client):
    resp = await client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
async def qa_log_id(pg_url):
    """Insert a dummy QA log and return its log_id."""
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    log_id = f"qalog_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(pg_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO qa_logs (log_id, session_id, user_id, scene, question, status, created_at) "
                "VALUES (:log_id, :sid, :uid, 'general', 'test?', 'success', :ts)"
            ),
            {
                "log_id": log_id,
                "sid": f"sess_{uuid.uuid4().hex[:8]}",
                "uid": "u_admin",
                "ts": datetime.now(timezone.utc),
            },
        )
    await engine.dispose()
    return log_id


@pytest.mark.asyncio
async def test_submit_feedback_success(client, auth_headers, qa_log_id):
    resp = await client.post(
        "/api/v1/feedback",
        json={
            "log_id": qa_log_id,
            "feedback_type": "thumbs_up",
            "comment": "回答准确",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["log_id"] == qa_log_id
    assert body["feedback_type"] == "thumbs_up"
    assert "feedback_id" in body


@pytest.mark.asyncio
async def test_submit_feedback_duplicate_rejected(client, auth_headers, qa_log_id):
    # First submission
    await client.post(
        "/api/v1/feedback",
        json={"log_id": qa_log_id, "feedback_type": "thumbs_up"},
        headers=auth_headers,
    )
    # Duplicate
    resp = await client.post(
        "/api/v1/feedback",
        json={"log_id": qa_log_id, "feedback_type": "thumbs_down"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_submit_feedback_invalid_log_id(client, auth_headers):
    resp = await client.post(
        "/api/v1/feedback",
        json={"log_id": "nonexistent_log_id", "feedback_type": "thumbs_up"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_feedback_invalid_type(client, auth_headers, qa_log_id):
    resp = await client.post(
        "/api/v1/feedback",
        json={"log_id": qa_log_id, "feedback_type": "invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
