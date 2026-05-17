"""Create ES indices with IK analyzer + 1024-dim dense_vector.

Supports: qa_chunks, ticket_knowledge, sales_knowledge, ops_knowledge.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.es_client import close_es, get_es

# All knowledge-base indices share the same mapping.
# Each index is configured per-agent via AgentConfig.es_index.
_INDEX_NAMES = [
    "qa_chunks",
    "ticket_knowledge",
    "sales_knowledge",
    "ops_knowledge",
]

# ---------------------------------------------------------------------------
# Shared mapping definition
# ---------------------------------------------------------------------------

def _index_body() -> dict:
    """Build index body with IK analyzer for Chinese text fields."""
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "ik_max_word_custom": {
                        "type": "custom",
                        "tokenizer": "ik_max_word",
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "doc_name": {
                    "type": "text",
                    "analyzer": "ik_max_word_custom",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "chunk_index": {"type": "integer"},
                "content": {
                    "type": "text",
                    "analyzer": "ik_max_word_custom",
                },
                "section": {
                    "type": "text",
                    "analyzer": "ik_max_word_custom",
                },
                "content_type": {"type": "keyword"},
                "page": {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1024,
                    "similarity": "cosine",
                    "index": True,
                },
                "permission_level": {"type": "keyword"},
                "department": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "knowledge_base": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "updated_at": {"type": "date"},
                "content_hash": {"type": "keyword"},
            }
        },
    }


def _index_body_standard() -> dict:
    """Fallback without IK analyzer."""
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "doc_name": {
                    "type": "text",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "chunk_index": {"type": "integer"},
                "content": {"type": "text"},
                "section": {"type": "text"},
                "content_type": {"type": "keyword"},
                "page": {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1024,
                    "similarity": "cosine",
                    "index": True,
                },
                "permission_level": {"type": "keyword"},
                "department": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "knowledge_base": {"type": "keyword"},
                "tags": {"type": "keyword"},
                "updated_at": {"type": "date"},
                "content_hash": {"type": "keyword"},
            }
        },
    }


async def ensure_index(index_name: str | None = None) -> None:
    """Create one or all knowledge-base ES indices."""
    es = get_es()
    names = [index_name] if index_name else _INDEX_NAMES

    for name in names:
        exists = await es.indices.exists(index=name)
        if exists:
            print(f"[init_es] index '{name}' already exists — skip")
            continue
        try:
            await es.indices.create(index=name, body=_index_body())
            print(f"[init_es] index '{name}' created (with IK analyzer)")
        except Exception:
            if not await es.indices.exists(index=name):
                await es.indices.create(index=name, body=_index_body_standard())
                print(f"[init_es] index '{name}' created (standard analyzer, IK unavailable)")


async def main() -> None:
    try:
        await ensure_index()
    finally:
        await close_es()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
