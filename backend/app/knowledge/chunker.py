"""Chapter-aware chunker with type-aware block processing.

Supports both legacy ``list[dict]`` input (``chunk_text``) and rich
``list[ParsedBlock]`` input (``chunk_blocks``) from layout-aware parsers.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Union

from app.config import get_settings

_sentence_re = re.compile(r"(?<=[。！？；.!?;])\s*")
_is_chinese = re.compile(r"[一-鿿㐀-䶿豈-﫿]")

# Maximum number of characters in a table chunk before truncation.
# Tables larger than this are truncated rather than split (tables lose
# semantics when cut in half).
MAX_TABLE_CHARS = 3000


@dataclass
class Chunk:
    index: int
    content: str
    section: str = ""
    content_hash: str = ""
    content_type: str = "text"
    """Content type: ``"text"`` | ``"table"`` | ``"image_description"``."""
    page: int = 0
    """1-based page number (0 if unknown)."""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.md5(
                self.content.encode("utf-8"), usedforsecurity=False
            ).hexdigest()


# ------------------------------------------------------------------
# Legacy API — list[dict] from simple parsers (MD, TXT)
# ------------------------------------------------------------------


def chunk_text(
    paragraphs: list[dict[str, Any]],
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """Split text paragraphs into chunks respecting sentence boundaries.

    Compatible with the legacy parser output: ``[{"text": ..., "section": ...}]``.
    """
    settings = get_settings()
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    sentences: list[tuple[str, str, str]] = []  # (text, section, content_type)
    for p in paragraphs:
        content_type = p.get("block_type", "text")
        for sent in _split_sentences(p["text"]):
            if sent:
                sentences.append((sent, p.get("section", ""), content_type))

    if not sentences:
        return []

    return _build_chunks(sentences, chunk_size, overlap)


# ------------------------------------------------------------------
# New API — list[ParsedBlock] from layout-aware parsers (PDF, DOCX)
# ------------------------------------------------------------------


def chunk_blocks(
    blocks: list[Any],  # list[ParsedBlock] (lazy import to avoid circular dep)
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """Split rich ParsedBlocks into chunks with type-aware processing.

    Rules:
    - **Table blocks**: kept as single chunks (never split). Truncated if
      they exceed ``MAX_TABLE_CHARS``.
    - **Image blocks**: each description becomes its own chunk with
      ``content_type="image_description"``.
    - **Text blocks**: split into sentences for sliding-window chunking.
      Heading blocks (``content_type="heading"`` in metadata) propagate
      as section prefixes for subsequent content.
    """
    settings = get_settings()
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    chunks: list[Chunk] = []
    idx = 0

    # ---- Phase 1: chunk tables and images individually ----
    # Collect text blocks for sentence-level chunking in phase 2
    pending_sentences: list[tuple[str, str, str, int, dict]] = []

    current_headings: list[str] = []

    for block in blocks:
        # Resolve block attributes — support both ParsedBlock and dict
        content = _get_attr(block, "content", "")
        block_type = _get_attr(block, "block_type", "text")
        section = _get_attr(block, "section", "")
        page = _get_attr(block, "page", 0)
        metadata = _get_attr(block, "metadata", {})

        # Update heading stack
        if metadata.get("content_type") == "heading":
            heading_text = content
            level = metadata.get("heading_level", 1)
            while len(current_headings) >= level:
                current_headings.pop()
            current_headings.append(heading_text)
            # Emit heading as its own small chunk
            chunks.append(Chunk(
                index=idx, content=heading_text,
                section=" > ".join(current_headings[:-1]) if len(current_headings) > 1 else "",
                content_type="text", page=page,
                metadata={"content_type": "heading", "heading_level": level},
            ))
            idx += 1
            continue

        # Merge section from TOC with detected headings
        if current_headings:
            prefix = " > ".join(current_headings)
            section = f"{prefix} > {section}" if section else prefix

        # ---- Table blocks: keep intact ----
        if block_type == "table":
            table_text = content
            if len(content) > MAX_TABLE_CHARS:
                table_text = content[:MAX_TABLE_CHARS] + "\n\n[表格过大，已截断]"
            chunks.append(Chunk(
                index=idx, content=table_text,
                section=section, content_type="table",
                page=page, metadata={"content_type": "table", "truncated": len(content) > MAX_TABLE_CHARS},
            ))
            idx += 1
            continue

        # ---- Image blocks: standalone chunk ----
        if block_type == "image":
            image_text = content or "[图片]"
            chunks.append(Chunk(
                index=idx, content=image_text,
                section=section, content_type="image_description",
                page=page, metadata={**metadata, "content_type": "image_description"},
            ))
            idx += 1
            continue

        # ---- Text blocks: accumulate for sentence-level chunking ----
        for sent in _split_sentences(content):
            if sent:
                pending_sentences.append((sent, section, block_type, page, metadata))

    # ---- Phase 2: chunk text sentences with sliding window ----
    if pending_sentences:
        text_chunks = _build_chunks_from_tuples(
            pending_sentences, chunk_size, overlap, idx
        )
        chunks.extend(text_chunks)
        idx = chunks[-1].index + 1 if chunks else idx

    # ---- Phase 3: re-index sequentially ----
    for i, c in enumerate(chunks):
        c.index = i

    return chunks


# ------------------------------------------------------------------
# Internal: chunk builders
# ------------------------------------------------------------------


def _build_chunks(
    sentences: list[tuple[str, str, str]],
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """Build chunks from (text, section, content_type) tuples."""
    # Convert to 5-tuple form for unified processing
    expanded = [(t, s, ct, 0, {}) for t, s, ct in sentences]
    return _build_chunks_from_tuples(expanded, chunk_size, overlap, 0)


def _build_chunks_from_tuples(
    sentences: list[tuple[str, str, str, int, dict]],
    chunk_size: int,
    overlap: int,
    start_index: int,
) -> list[Chunk]:
    """Build chunks from (text, section, content_type, page, metadata) tuples."""
    if not sentences:
        return []

    chunks: list[Chunk] = []
    idx = start_index
    current: list[str] = []
    current_sections: list[str] = []
    current_pages: list[int] = []
    current_tokens = 0

    for text, section, content_type, page, metadata in sentences:
        tokens = estimate_token_count(text)

        if current and current_tokens + tokens > chunk_size:
            content = "".join(current)
            section_merged = " | ".join(sorted(set(s for s in current_sections if s)))
            page_num = current_pages[0] if current_pages else 0
            chunks.append(Chunk(
                index=idx, content=content, section=section_merged,
                content_type=content_type, page=page_num,
            ))
            idx += 1

            # Overlap: keep last N tokens worth of sentences
            overlap_sents = _backtrack_overlap_tuples(current, overlap, sentences)
            current = [s[0] for s in overlap_sents]
            current_sections = [s[1] for s in overlap_sents]
            current_pages = [s[3] for s in overlap_sents]
            current_tokens = estimate_token_count("".join(current))

        current.append(text)
        if section:
            current_sections.append(section)
        if page:
            current_pages.append(page)
        current_tokens += tokens

    if current:
        content = "".join(current)
        section_merged = " | ".join(sorted(set(s for s in current_sections if s)))
        page_num = current_pages[0] if current_pages else 0
        # Use content_type from the primary block type of the input
        final_ct = sentences[0][2] if sentences else "text"
        chunks.append(Chunk(
            index=idx, content=content, section=section_merged,
            content_type=final_ct, page=page_num,
        ))

    return chunks


def _backtrack_overlap_tuples(
    current: list[str],
    overlap_tokens: int,
    sentences: list[tuple[str, str, str, int, dict]],
) -> list[tuple[str, str, str, int, dict]]:
    """Like _backtrack_for_overlap but returns full tuples to preserve metadata."""
    if not current:
        return []
    tokens = 0
    result: list[tuple[str, str, str, int, dict]] = []
    # Find matching sentences from the end of `current`
    remaining = list(current)
    while remaining and tokens < overlap_tokens:
        for s in reversed(sentences):
            if remaining and s[0] == remaining[-1]:
                result.insert(0, s)
                tokens += estimate_token_count(s[0])
                remaining.pop()
                break
        else:
            break
    return result


# ------------------------------------------------------------------
# Token estimation utilities (public, used by tests)
# ------------------------------------------------------------------


def estimate_token_count(text: str) -> int:
    """Estimate token count: Chinese ~1.5 chars/token, English ~4 chars/token."""
    cn = len(_is_chinese.findall(text))
    en = len(text) - cn
    return max(1, int(cn / 1.5 + en / 4.0))


def _split_sentences(text: str) -> list[str]:
    """Split text at sentence-ending punctuation."""
    parts = _sentence_re.split(text)
    result: list[str] = []
    buffer = ""
    for p in parts:
        if not p:
            continue
        buffer += p
        if p[-1] in "。！？；.!?;":
            result.append(buffer)
            buffer = ""
    if buffer:
        result.append(buffer)
    return result


def _get_attr(obj: Any, name: str, default: Any = "") -> Any:
    """Get attribute from a ParsedBlock or dict, with a default."""
    if hasattr(obj, name) and not callable(getattr(obj, name)):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _backtrack_for_overlap(current: list[str], overlap_tokens: int) -> list[str]:
    """Collect sentences from the end of *current* totalling *overlap_tokens*."""
    if not current:
        return []
    result: list[str] = []
    tokens = 0
    for s in reversed(current):
        result.insert(0, s)
        tokens += estimate_token_count(s)
        if tokens >= overlap_tokens:
            break
    return result
