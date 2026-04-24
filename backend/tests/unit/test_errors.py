import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.errors import ErrorCode, install_exception_handlers


def _make_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/bad-request")
    async def _bad():
        raise HTTPException(
            status_code=400,
            detail={"code": ErrorCode.BAD_REQUEST, "message": "参数非法"},
        )

    @app.get("/unauthorized")
    async def _unauth():
        raise HTTPException(
            status_code=401,
            detail={"code": ErrorCode.TOKEN_EXPIRED, "message": "Token 失效"},
        )

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("unexpected")

    return app


@pytest.mark.asyncio
async def test_http_exception_wrapped_into_standard_shape():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/bad-request")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == 40001
    assert body["message"] == "参数非法"
    assert "trace_id" in body


@pytest.mark.asyncio
async def test_unhandled_exception_becomes_500_shape():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t") as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] >= 50000
    assert "trace_id" in body


def test_error_code_enum_covers_spec_categories():
    assert ErrorCode.BAD_REQUEST == 40001
    assert ErrorCode.TOKEN_EXPIRED == 40101
    assert ErrorCode.ACCOUNT_DISABLED == 40102
    assert ErrorCode.PERMISSION_DENIED == 40301
    assert ErrorCode.RATE_LIMITED == 42900


@pytest.mark.asyncio
async def test_unknown_route_still_returns_404_not_500():
    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/nonexistent-path-xyz")
    assert r.status_code == 404
