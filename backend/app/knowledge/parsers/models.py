"""ParsedBlock — rich content block with type, position, and visual metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedBlock:
    """A parsed content block from document parsing.

    Extends the legacy ``{"text": str, "section": str}`` dict with block_type,
    page coordinates, and optional image data for vision-LLM description.
    """

    content: str
    """Main text content. For text blocks: paragraph text. For tables: Markdown table. For images: vision-LLM description."""

    block_type: str = "text"
    """Content type: ``"text"`` | ``"table"`` | ``"image"``."""

    section: str = ""
    """Section heading hierarchy, e.g. ``"第一章 > 1.1 概述"``."""

    page: int = 0
    """1-based page number (PDF/DOCX sources)."""

    bbox: tuple[float, float, float, float] | None = None
    """Page coordinates (x0, y0, x1, y1) for reading-order sorting."""

    image_base64: str = ""
    """Base64-encoded PNG image data (only for image blocks)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extension metadata: ``content_type``, ``source_index``, ``img_format``, etc."""

    def to_paragraph_dict(self) -> dict[str, Any]:
        """Convert to the legacy paragraph dict compatible with chunk_text().

        Includes extra keys (block_type, page, metadata) that enhanced
        pipelines can consume.
        """
        d: dict[str, Any] = {
            "text": self.content,
            "section": self.section,
        }
        if self.block_type != "text":
            d["block_type"] = self.block_type
        if self.page:
            d["page"] = self.page
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @staticmethod
    def sorted_by_position(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        """Sort blocks by page → y → x (top-to-bottom, left-to-right)."""
        def _key(b: ParsedBlock) -> tuple:
            if b.bbox:
                return (b.page, b.bbox[1], b.bbox[0])
            return (b.page, 0, 0)
        return sorted(blocks, key=_key)
