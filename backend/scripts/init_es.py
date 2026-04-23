"""Create qa_chunks index with IK analyzer + 1024-dim dense_vector."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.storage.es_client import close_es, get_es

INDEX_NAME = "qa_chunks"
INDEX_BODY: dict = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "ik_smart_plus": {"type": "custom", "tokenizer": "ik_smart"}
            }
        },
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "doc_name": {"type": "keyword"},
            "chunk_index": {"type": "integer"},
            "content": {"type": "text", "analyzer": "ik_smart_plus"},
            "section": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": 1024,
                "similarity": "cosine",
                "index": True,
            },
            "permission_level": {"type": "keyword"},
            "department": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "updated_at": {"type": "date"},
            "content_hash": {"type": "keyword"},
        }
    },
}


async def ensure_index() -> None:
    es = get_es()
    exists = await es.indices.exists(index=INDEX_NAME)
    if exists:
        print(f"[init_es] index '{INDEX_NAME}' already exists - skip")
        return
    await es.indices.create(index=INDEX_NAME, body=INDEX_BODY)
    print(f"[init_es] index '{INDEX_NAME}' created")


async def main() -> None:
    try:
        await ensure_index()
    finally:
        await close_es()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
