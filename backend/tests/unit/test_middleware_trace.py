"""Unit tests for TraceIDMiddleware."""

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def trace_app():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    from app.middleware.trace import TraceIDMiddleware

    app = FastAPI()
    app.add_middleware(TraceIDMiddleware)

    @app.get("/ok")
    async def ok(request: Request):
        return {"trace_id": getattr(request.state, "trace_id", None)}

    @app.get("/error")
    async def error():
        raise RuntimeError("boom")

    return app


@pytest.fixture
async def client(trace_app):
    async with AsyncClient(
        transport=ASGITransport(app=trace_app), base_url="http://t"
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_trace_id_injected_on_success(client):
    resp = await client.get("/ok")
    assert resp.status_code == 200
    assert "x-trace-id" in resp.headers
    assert resp.headers["x-trace-id"].startswith("tr_")
    body = resp.json()
    assert body["trace_id"] == resp.headers["x-trace-id"]


@pytest.mark.asyncio
async def test_trace_id_injected_on_error(client):
    resp = await client.get("/error")
    assert resp.status_code == 500
    # Even on errors, the trace_id header should be present
    assert "x-trace-id" in resp.headers
    assert resp.headers["x-trace-id"].startswith("tr_")


@pytest.mark.asyncio
async def test_trace_id_unique_per_request(client):
    ids: set[str] = set()
    for _ in range(5):
        resp = await client.get("/ok")
        ids.add(resp.headers["x-trace-id"])
    assert len(ids) == 5
