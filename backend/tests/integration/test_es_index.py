import pytest

from app.storage.es_client import close_es, get_es

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_es_ping(es_url, monkeypatch):
    monkeypatch.setenv("ES_URL", es_url)
    from app.config import get_settings
    get_settings.cache_clear()
    await close_es()
    client = get_es()
    info = await client.info()
    assert "version" in info
    await close_es()


@pytest.mark.asyncio
async def test_init_es_creates_qa_chunks(es_url, monkeypatch):
    monkeypatch.setenv("ES_URL", es_url)
    from app.config import get_settings
    get_settings.cache_clear()
    await close_es()
    from scripts.init_es import ensure_index
    await ensure_index()
    client = get_es()
    mapping = await client.indices.get_mapping(index="qa_chunks")
    props = mapping["qa_chunks"]["mappings"]["properties"]
    assert props["embedding"]["type"] == "dense_vector"
    assert props["embedding"]["dims"] == 1024
    assert props["content"]["type"] == "text"
    assert props["permission_level"]["type"] == "keyword"
    await close_es()
