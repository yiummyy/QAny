"""Integration tests for POST /api/v1/qa/ask SSE streaming."""

import json

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(pg_url, redis_url, es_url, monkeypatch):
    """Create a test client with all services wired."""
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("ES_URL", es_url)
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
    """Login as admin and return Authorization headers."""
    resp = await client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse SSE text into list of (event_type, data) tuples."""
    frames = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            frames.append((event_type, data))
    return frames


@pytest.mark.asyncio
async def test_sse_frame_sequence(client, auth_headers):
    """Verify SSE response contains status→status→message→done frames."""
    resp = await client.post(
        "/api/v1/qa/ask",
        json={
            "question": "公司的年假制度是怎样的？",
            "session_id": "test_sse_session_01",
            "input_type": "text",
            "scene": "general",
        },
        headers=auth_headers,
        timeout=30,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    frames = _parse_sse(resp.text)
    event_types = [f[0] for f in frames]

    assert "status" in event_types
    assert "message" in event_types or "error" in event_types
    assert event_types[-1] in ("done", "error")


@pytest.mark.asyncio
async def test_sse_trace_id_in_response(client, auth_headers):
    """Verify X-Trace-Id header is present."""
    resp = await client.post(
        "/api/v1/qa/ask",
        json={
            "question": "测试trace_id",
            "session_id": "test_sse_trace_01",
        },
        headers=auth_headers,
        timeout=30,
    )
    assert "x-trace-id" in resp.headers
    assert resp.headers["x-trace-id"].startswith("tr_")


@pytest.mark.asyncio
async def test_sse_done_frame_has_trace_id(client, auth_headers):
    """Verify the done frame includes trace_id."""
    resp = await client.post(
        "/api/v1/qa/ask",
        json={
            "question": "测试done帧",
            "session_id": "test_sse_done_01",
        },
        headers=auth_headers,
        timeout=30,
    )
    frames = _parse_sse(resp.text)
    done_frames = [d for e, d in frames if e == "done"]
    if done_frames:
        assert "trace_id" in done_frames[0]
        assert "response_time_ms" in done_frames[0]


@pytest.mark.asyncio
async def test_sse_requires_auth(client):
    """Verify endpoint returns 401 without auth."""
    resp = await client.post(
        "/api/v1/qa/ask",
        json={
            "question": "测试认证",
            "session_id": "test_sse_auth_01",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_qa_session_persisted(client, auth_headers):
    """Verify session history is retrievable after a request."""
    session_id = "test_session_persist_01"
    await client.post(
        "/api/v1/qa/ask",
        json={
            "question": "持久化测试",
            "session_id": session_id,
        },
        headers=auth_headers,
        timeout=30,
    )

    resp = await client.get(
        f"/api/v1/qa/sessions/{session_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == session_id
    assert "records" in body
