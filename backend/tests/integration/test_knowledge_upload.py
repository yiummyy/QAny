"""Integration tests for knowledge upload + indexing + deletion."""

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration


@pytest.fixture
async def admin_client(pg_url, es_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("ES_URL", es_url)
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
        r = await c.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        token = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    # Cleanup
    from app.storage.es_client import close_es, get_es
    es = get_es()
    try:
        await es.delete_by_query(
            index="qa_chunks",
            body={"query": {"match_all": {}}},
            refresh=True,
        )
    except Exception:
        pass
    await close_es()

    from app.storage.pg import dispose_engine
    from app.storage.redis_client import close_redis, get_redis

    r2 = get_redis()
    for prefix in ("jwt_blacklist", "jwt_pair", "ratelimit"):
        async for key in r2.scan_iter(match=f"{prefix}:*"):
            await r2.delete(key)
    await close_redis()
    await dispose_engine()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_upload_txt_document(admin_client):
    files = {"file": ("test.txt", b"Hello World\n\nThis is a test document.", "text/plain")}
    r = await admin_client.post("/api/v1/knowledge/upload", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["doc_id"].startswith("doc_")
    assert data["status"] in ("pending", "indexed")


@pytest.mark.asyncio
async def test_upload_txt_document_with_permission(admin_client):
    files = {"file": ("test_L1.txt", b"Hello L1\n\nThis is a test document.", "text/plain")}
    data = {"permission_level": "L1"}
    r = await admin_client.post("/api/v1/knowledge/upload", files=files, data=data)
    assert r.status_code == 200
    resp_data = r.json()
    assert resp_data["doc_id"].startswith("doc_")
    
    # Verify permission level in list API
    r_list = await admin_client.get("/api/v1/knowledge/documents")
    assert r_list.status_code == 200
    docs = r_list.json()["items"]
    uploaded_doc = next((d for d in docs if d["doc_id"] == resp_data["doc_id"]), None)
    assert uploaded_doc is not None
    assert uploaded_doc["permission_level"] == "L1"


@pytest.mark.asyncio
async def test_upload_unsupported_type(admin_client):
    files = {"file": ("test.exe", b"binary", "application/octet-stream")}
    r = await admin_client.post("/api/v1/knowledge/upload", files=files)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_without_auth(pg_url, es_url, redis_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("ES_URL", es_url)
    monkeypatch.setenv("REDIS_URL", redis_url)
    monkeypatch.setenv("JWT_SECRET", "x" * 40)

    from app.config import get_settings
    get_settings.cache_clear()

    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as c:
        files = {"file": ("test.txt", b"content", "text/plain")}
        r = await c.post("/api/v1/knowledge/upload", files=files)
        assert r.status_code in (401, 403)

    from app.storage.pg import dispose_engine
    await dispose_engine()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_list_documents(admin_client):
    r = await admin_client.get("/api/v1/knowledge/documents")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_delete_nonexistent_document(admin_client):
    r = await admin_client.delete("/api/v1/knowledge/documents/doc_nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_upload_then_delete(admin_client):
    # Upload
    content = b"Test document for deletion\n\nSecond paragraph."
    files = {"file": ("delete_test.txt", content, "text/plain")}
    r = await admin_client.post("/api/v1/knowledge/upload", files=files)
    assert r.status_code == 200
    doc_id = r.json()["doc_id"]

    # Verify in list
    r = await admin_client.get("/api/v1/knowledge/documents")
    items = r.json()["items"]
    assert any(d["doc_id"] == doc_id for d in items)

    # Delete
    r = await admin_client.delete(f"/api/v1/knowledge/documents/{doc_id}")
    assert r.status_code == 200

    # Verify gone from list
    r = await admin_client.get("/api/v1/knowledge/documents")
    items = r.json()["items"]
    assert not any(d["doc_id"] == doc_id for d in items)
