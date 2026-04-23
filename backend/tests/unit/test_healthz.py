import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.storage.es_client import close_es
from app.storage.pg import dispose_engine
from app.storage.redis_client import close_redis


@pytest.fixture(autouse=True)
async def _reset_singletons():
    await close_es()
    await close_redis()
    await dispose_engine()
    yield
    await close_es()
    await close_redis()
    await dispose_engine()


@pytest.mark.asyncio
async def test_healthz_returns_degraded_without_backends():
    """单元环境下无真实 pg/redis/es，深度探活应返回 degraded 且 deps 齐全。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert set(body["deps"].keys()) == {"pg", "redis", "es"}
    assert body["deps"]["pg"] == "down"
    assert body["deps"]["redis"] == "down"
    assert body["deps"]["es"] == "down"
    assert body["env"] == "test"
