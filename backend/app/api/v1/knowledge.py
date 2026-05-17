"""Knowledge pipeline API — Spec §4.2."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, Form

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import UserClaims, require_admin
from app.config import get_settings
from app.knowledge.chunker import chunk_blocks, chunk_text
from app.knowledge.embedder import encode
from app.knowledge.indexer import delete_doc_chunks, index_chunks
from app.knowledge.parsers import get_layout_parser, get_parser
from app.knowledge.parsers.vision import describe_images
from app.models.document import Document
from app.storage.pg import get_db, get_sessionmaker

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".md", ".txt"}


class UploadResponse(BaseModel):
    doc_id: str
    title: str
    status: str
    message: str


class DocumentItem(BaseModel):
    doc_id: str
    title: str
    source_type: str
    knowledge_base: str
    tags: list[str] | None = None
    permission_level: str
    status: str
    chunk_count: int
    uploaded_by: str | None
    uploaded_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    total: int
    items: list[DocumentItem]


class SyncResponse(BaseModel):
    message: str
    document_count: int


def _make_doc_id() -> str:
    return "doc_" + uuid.uuid4().hex[:12]


def _compute_file_hash(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


async def _process_document(doc_id: str, doc_name: str, file_path: str) -> None:
    """Background pipeline: parse → (vision) → chunk → embed → index.

    For PDF/DOCX, uses layout-aware parsing with table/image extraction.
    For MD/TXT, uses legacy text-only parsing.
    """
    logger.info(f"开始处理文档: {doc_name} ({doc_id})")
    sessionmaker = get_sessionmaker()
    try:
        settings = get_settings()
        ext = Path(file_path).suffix.lower()

        # ---- Parse ----
        logger.info(f"文档 {doc_id} 开始解析 (ext={ext})...")
        layout_parser = get_layout_parser(ext)

        if layout_parser is not None:
            # Rich path: layout-aware parsing → vision → chunk_blocks
            blocks = layout_parser.parse_blocks(str(file_path))
            logger.info(
                f"文档 {doc_id} 版面解析完成: {len(blocks)} 个区块 "
                f"(text={sum(1 for b in blocks if b.block_type=='text')}, "
                f"table={sum(1 for b in blocks if b.block_type=='table')}, "
                f"image={sum(1 for b in blocks if b.block_type=='image')})"
            )

            # Vision: describe images if enabled
            if settings.vision_enabled and any(b.block_type == "image" for b in blocks):
                logger.info(f"文档 {doc_id} 开始视觉识别...")
                blocks = await describe_images(
                    blocks,
                    max_images=settings.vision_max_images_per_doc,
                    model=settings.vision_model,
                )
                logger.info(f"文档 {doc_id} 视觉识别完成")

            chunks = chunk_blocks(blocks)
        else:
            # Legacy path: text-only parsing → chunk_text
            parser = get_parser(ext)
            if parser is None:
                raise ValueError(f"Unsupported file type: {ext}")

            paragraphs = await parser.parse(str(file_path))
            chunks = chunk_text(paragraphs)

        logger.info(
            f"文档 {doc_id} 分块完成: {len(chunks)} 块 "
            f"(text={sum(1 for c in chunks if c.content_type=='text')}, "
            f"table={sum(1 for c in chunks if c.content_type=='table')}, "
            f"image={sum(1 for c in chunks if c.content_type=='image_description')})"
        )

        # ---- Embed ----
        logger.info(f"文档 {doc_id} 开始生成嵌入...")
        texts = [c.content for c in chunks]
        embeddings = await encode(texts)

        # ---- Index ----
        logger.info(f"文档 {doc_id} 嵌入完成，开始写入索引...")
        async with sessionmaker() as session:
            doc = await session.get(Document, doc_id)
            if doc is None:
                logger.warning(f"文档 {doc_id} 不存在于数据库，取消处理")
                return

            await delete_doc_chunks(doc_id, knowledge_base=doc.knowledge_base)
            chunk_count = await index_chunks(
                doc_id=doc_id,
                doc_name=doc_name,
                chunks=chunks,
                embeddings=embeddings,
                permission_level=doc.permission_level,
                department=doc.department,
                source_type=doc.source_type,
                knowledge_base=doc.knowledge_base,
                tags=doc.tags,
            )

            doc.chunk_count = chunk_count
            doc.status = "indexed"
            doc.updated_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info(f"文档 {doc_id} 处理成功，索引 {chunk_count} 块")

    except Exception as exc:
        logger.error(f"文档 {doc_id} 处理失败: {str(exc)}", exc_info=True)
        async with sessionmaker() as session:
            doc = await session.get(Document, doc_id)
            if doc:
                doc.status = "failed"
                doc.error_message = str(exc)[:500]
                doc.updated_at = datetime.now(timezone.utc)
                await session.commit()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    permission_level: str | None = Form(None),
    knowledge_base: str | None = Form("qa"),
    tags: str | None = Form(None),
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> UploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": 40001, "message": "缺少文件名"})

    from app.knowledge.kb_registry import validate_kb
    from app.knowledge.tag_registry import ALL_TAGS

    kb = validate_kb(knowledge_base or "qa")
    pl = permission_level if permission_level else claims.pl
    parsed_tags: list[str] | None = None
    if tags:
        raw = [t.strip() for t in tags.split(",") if t.strip()]
        parsed_tags = [t for t in raw if t in ALL_TAGS]
        if unknown := [t for t in raw if t not in ALL_TAGS]:
            logger.warning("上传文档时包含未知标签，已过滤: %s", unknown)
    if pl not in {"L1", "L2", "L3"}:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": f"无效的权限级别: {pl}"},
        )

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={"code": 40001, "message": f"不支持的文件类型: {ext}"},
        )

    settings = get_settings()
    upload_dir = Path(settings.data_dir) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}_{file.filename}"
    stored_path = upload_dir / stored_name

    content = await file.read()
    stored_path.write_bytes(content)

    file_hash = _compute_file_hash(stored_path)

    result = await session.execute(
        select(Document).where(Document.file_hash == file_hash)
    )
    existing = result.scalar_one_or_none()
    if existing:
        stored_path.unlink(missing_ok=True)
        return UploadResponse(
            doc_id=existing.doc_id,
            title=existing.title,
            status=existing.status,
            message="文档已存在，跳过重复上传",
        )

    doc_id = _make_doc_id()
    now = datetime.now(timezone.utc)
    doc = Document(
        doc_id=doc_id,
        title=file.filename,
        source_type=ext.lstrip("."),
        file_path=str(stored_path),
        file_hash=file_hash,
        knowledge_base=kb,
        tags=parsed_tags,
        permission_level=pl,
        department=claims.dept,
        status="pending",
        uploaded_by=claims.sub,
        uploaded_at=now,
        updated_at=now,
    )
    session.add(doc)
    await session.commit()

    background_tasks.add_task(_process_document, doc_id, file.filename, str(stored_path))

    return UploadResponse(
        doc_id=doc_id,
        title=file.filename,
        status="pending",
        message="文档已上传，正在后台处理",
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    offset: int = 0,
    limit: int = 20,
    status_filter: str | None = None,
    permission_level: str | None = None,
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    base = select(Document)
    if status_filter:
        base = base.where(Document.status == status_filter)
    if permission_level:
        base = base.where(Document.permission_level == permission_level)

    count_query = select(text("count(*)")).select_from(base.subquery())
    total = (await session.execute(count_query)).scalar_one()

    rows = (await session.execute(
        base.order_by(Document.uploaded_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    items = [
        DocumentItem(
            doc_id=d.doc_id,
            title=d.title,
            source_type=d.source_type,
            knowledge_base=d.knowledge_base,
            tags=d.tags,
            permission_level=d.permission_level,
            status=d.status,
            chunk_count=d.chunk_count,
            uploaded_by=d.uploaded_by,
            uploaded_at=d.uploaded_at.isoformat(),
            updated_at=d.updated_at.isoformat(),
        )
        for d in rows
    ]
    return DocumentListResponse(total=total, items=items)


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"code": 40001, "message": "文档不存在"})

    file_path = Path(doc.file_path)
    file_path.unlink(missing_ok=True)

    await delete_doc_chunks(doc_id, knowledge_base=doc.knowledge_base)

    doc_id_ref = doc.doc_id
    title = doc.title
    await session.delete(doc)
    await session.commit()

    return {"doc_id": doc_id_ref, "title": title, "message": "文档已删除"}


@router.get("/documents/{doc_id}/content")
async def get_document_content(
    doc_id: str,
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict:
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"code": 40001, "message": "文档不存在"})

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail={"code": 40002, "message": "文件实体已丢失"})

    ext = "." + doc.source_type
    layout_parser = get_layout_parser(ext)

    try:
        if layout_parser is not None:
            blocks = layout_parser.parse_blocks(str(file_path))
            # Render rich blocks with type markers
            parts: list[str] = []
            for b in blocks:
                if b.block_type == "table":
                    parts.append(f"[表格]\n{b.content}")
                elif b.block_type == "image":
                    parts.append(b.content or "[图片]")
                else:
                    parts.append(b.content)
            full_text = "\n\n".join(parts)
        else:
            parser = get_parser(ext)
            if not parser:
                raise HTTPException(status_code=400, detail={"code": 40003, "message": "不支持的文件类型"})
            blocks = await parser.parse(str(file_path))
            full_text = "\n\n".join([b.get("text", "") for b in blocks])

        return {"doc_id": doc.doc_id, "title": doc.title, "content": full_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": 50000, "message": f"解析文件失败: {str(e)}"})


@router.post("/sync", response_model=SyncResponse)
async def sync_knowledge(
    background_tasks: BackgroundTasks,
    claims: UserClaims = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> SyncResponse:
    # 包含 pending、indexed、failed 状态的文档都可以被重置和重新处理
    result = await session.execute(
        select(Document).where(Document.status.in_(["pending", "indexed", "failed"]))
    )
    docs = result.scalars().all()

    for doc in docs:
        doc.status = "pending"
        doc.updated_at = datetime.now(timezone.utc)
        background_tasks.add_task(_process_document, doc.doc_id, doc.title, doc.file_path)
    await session.commit()

    return SyncResponse(
        message=f"已重置并重新调度 {len(docs)} 个文档的后台处理任务",
        document_count=len(docs),
    )
