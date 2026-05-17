"""Rebuild ES qa_chunks from PG documents table."""
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.knowledge.chunker import chunk_text
from app.knowledge.embedder import encode
from app.knowledge.indexer import delete_doc_chunks, index_chunks
from app.knowledge.parsers import get_parser
from app.models.document import Document
from app.storage.es_client import close_es
from app.storage.pg import dispose_engine, get_sessionmaker


async def reindex(doc_id: str | None = None) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        query = select(Document)
        if doc_id:
            query = query.where(Document.doc_id == doc_id)
        result = await session.execute(query)
        docs = result.scalars().all()

    if not docs:
        print("[reindex] No documents found")
        return

    total_chunks = 0
    t0 = time.monotonic()

    for doc in docs:
        print(f"[reindex] Processing {doc.doc_id} ({doc.title})")
        file_path = Path(doc.file_path)
        if not file_path.exists():
            print(f"[reindex] WARNING: file not found {doc.file_path}, skipping")
            continue

        ext = file_path.suffix.lower()
        parser = get_parser(ext)
        if parser is None:
            print(f"[reindex] WARNING: no parser for {ext}, skipping {doc.doc_id}")
            continue

        try:
            paragraphs = await parser.parse(str(file_path))
            chunks = chunk_text(paragraphs)
            texts = [c.content for c in chunks]
            embeddings = await encode(texts)

            await delete_doc_chunks(doc.doc_id)
            count = await index_chunks(
                doc_id=doc.doc_id,
                doc_name=doc.title,
                chunks=chunks,
                embeddings=embeddings,
                permission_level=doc.permission_level,
                department=doc.department,
                source_type=doc.source_type,
            )

            async with sessionmaker() as session:
                d = await session.get(Document, doc.doc_id)
                if d:
                    d.chunk_count = count
                    d.status = "indexed"
                    d.error_message = None
                    await session.commit()

            total_chunks += count
            print(f"[reindex]   indexed {count} chunks")

        except Exception as exc:
            print(f"[reindex] ERROR on {doc.doc_id}: {exc}")
            async with sessionmaker() as session:
                d = await session.get(Document, doc.doc_id)
                if d:
                    d.status = "failed"
                    d.error_message = str(exc)[:500]
                    await session.commit()

    elapsed = time.monotonic() - t0
    print(f"[reindex] Done: {len(docs)} docs, {total_chunks} chunks in {elapsed:.1f}s")


async def main() -> None:
    doc_id = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        await reindex(doc_id)
    finally:
        await close_es()
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
