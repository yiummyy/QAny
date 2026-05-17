"""Integration tests for ES indexer operations."""
import numpy as np
import pytest

from app.knowledge.chunker import Chunk
from app.knowledge.indexer import delete_doc_chunks, index_chunks
from app.storage.es_client import close_es, get_es

pytestmark = pytest.mark.integration


def _make_chunks(n: int) -> list[Chunk]:
    return [
        Chunk(
            index=i,
            content=f"Chunk {i}: This is test content for chunk number {i}.",
            section=f"Section {i % 3}",
        )
        for i in range(n)
    ]


def _make_embeddings(n: int, dim: int = 1024) -> np.ndarray:
    rng = np.random.default_rng(42)
    embeddings = rng.random((n, dim)).astype(np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    return embeddings / norms


@pytest.mark.asyncio
async def test_index_and_delete_chunks(es_url, monkeypatch):
    monkeypatch.setenv("ES_URL", es_url)
    from app.config import get_settings
    get_settings.cache_clear()
    await close_es()

    doc_id = "test_doc_001"
    chunks = _make_chunks(5)
    embeddings = _make_embeddings(5)

    # Index
    count = await index_chunks(
        doc_id=doc_id,
        doc_name="Test Document",
        chunks=chunks,
        embeddings=embeddings,
        permission_level="L2",
        department="Engineering",
        source_type="txt",
    )
    assert count == 5

    # Verify in ES
    es = get_es()
    await es.indices.refresh(index="qa_chunks")
    resp = await es.search(
        index="qa_chunks",
        body={"query": {"term": {"doc_id": doc_id}}, "size": 10},
    )
    assert resp["hits"]["total"]["value"] == 5
    hit = resp["hits"]["hits"][0]["_source"]
    assert hit["doc_id"] == doc_id
    assert hit["permission_level"] == "L2"
    assert hit["department"] == "Engineering"

    # Verify embedding exists
    assert len(hit["embedding"]) == 1024

    # Delete
    deleted = await delete_doc_chunks(doc_id)
    assert deleted > 0

    # Verify gone
    await es.indices.refresh(index="qa_chunks")
    resp = await es.search(
        index="qa_chunks",
        body={"query": {"term": {"doc_id": doc_id}}},
    )
    assert resp["hits"]["total"]["value"] == 0

    await close_es()
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_chunk_idempotent_reinsert(es_url, monkeypatch):
    """Re-indexing the same doc should not create duplicates."""
    monkeypatch.setenv("ES_URL", es_url)
    from app.config import get_settings
    get_settings.cache_clear()
    await close_es()

    doc_id = "test_doc_idem"
    chunks = _make_chunks(3)
    embeddings = _make_embeddings(3)

    # Insert twice
    await delete_doc_chunks(doc_id)
    await index_chunks(doc_id, "Test", chunks, embeddings, "L1", None, "txt")
    await delete_doc_chunks(doc_id)
    await index_chunks(doc_id, "Test", chunks, embeddings, "L1", None, "txt")

    es = get_es()
    await es.indices.refresh(index="qa_chunks")
    resp = await es.search(
        index="qa_chunks",
        body={"query": {"term": {"doc_id": doc_id}}},
    )
    assert resp["hits"]["total"]["value"] == 3

    await close_es()
    get_settings.cache_clear()
