from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import numpy as np

from app.knowledge.chunker import Chunk
from app.knowledge.kb_registry import get_index_for_kb, validate_kb
from app.storage.es_client import get_es

logger = logging.getLogger(__name__)


def make_chunk_id(doc_id: str, chunk_index: int, content_hash: str) -> str:
    raw = f"{doc_id}|{chunk_index}|{content_hash}"
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


async def delete_doc_chunks(doc_id: str, knowledge_base: str = "qa") -> int:
    index_name = get_index_for_kb(knowledge_base)
    es = get_es()
    try:
        resp = await es.delete_by_query(
            index=index_name,
            body={"query": {"term": {"doc_id": doc_id}}},
            refresh=True,
        )
    except Exception:
        # Index may not exist yet (e.g., no documents uploaded to this KB)
        logger.warning("Failed to delete chunks for doc %s from %s (index may not exist)", doc_id, index_name)
        return 0
    deleted = resp.get("deleted", 0)
    if deleted:
        logger.info("Deleted %d chunks for doc %s from %s", deleted, doc_id, index_name)
    return deleted


async def index_chunks(
    doc_id: str,
    doc_name: str,
    chunks: list[Chunk],
    embeddings: np.ndarray,
    permission_level: str,
    department: str | None,
    source_type: str,
    knowledge_base: str = "qa",
    tags: list[str] | None = None,
) -> int:
    if not chunks:
        return 0

    index_name = get_index_for_kb(validate_kb(knowledge_base))
    es = get_es()
    now = datetime.now(timezone.utc).isoformat()
    actions: list[dict] = []

    for chunk in chunks:
        action = {
            "index": {
                "_index": index_name,
                "_id": make_chunk_id(doc_id, chunk.index, chunk.content_hash),
            }
        }
        doc = {
            "chunk_id": make_chunk_id(doc_id, chunk.index, chunk.content_hash),
            "doc_id": doc_id,
            "doc_name": doc_name,
            "chunk_index": chunk.index,
            "content": chunk.content,
            "section": chunk.section,
            "content_type": chunk.content_type,
            "page": chunk.page,
            "embedding": embeddings[chunk.index].tolist(),
            "permission_level": permission_level,
            "department": department or "",
            "source_type": source_type,
            "knowledge_base": knowledge_base,
            "tags": tags or [],
            "updated_at": now,
            "content_hash": chunk.content_hash,
        }
        actions.extend([action, doc])

    from elasticsearch import ApiError

    try:
        resp = await es.bulk(body=actions, refresh=True)
        if resp.get("errors"):
            error_items = [i for i in resp.get("items", []) if "error" in i.get("index", {})]
            logger.error("Bulk index errors for doc %s: %s", doc_id, error_items[:3])
        indexed = len(chunks)
        logger.info("Indexed %d chunks for doc %s", indexed, doc_id)
        return indexed
    except ApiError:
        logger.exception("ES bulk insert failed for doc %s", doc_id)
        raise
