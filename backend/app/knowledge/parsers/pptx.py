"""PPTX parser — slide-aware text + table + image extraction.

Capabilities:
- Slide text extraction with reading-order sorting (top-to-bottom, left-to-right)
- Slide title detection → section hierarchy
- Table detection within slides → Markdown
- Embedded image extraction → base64 for vision-LLM description
- Speaker notes extraction (appended as supplementary content)
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import zipfile
from typing import Any

from pptx import Presentation as PptxPresentation
from pptx.shapes.base import BaseShape
from pptx.shapes.picture import Picture
from pptx.table import Table as PptxTable

from app.knowledge.parsers.base import BaseParser
from app.knowledge.parsers.models import ParsedBlock

logger = logging.getLogger(__name__)

# pptx namespace for extracting image rIds from shape XML
_PPTX_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


class PptxParser(BaseParser):
    """Slide-aware PPTX parser with table, image, and note extraction."""

    async def parse(self, file_path: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        blocks = await loop.run_in_executor(None, self._parse_sync, file_path)
        return [b.to_paragraph_dict() for b in blocks]

    def parse_blocks(self, file_path: str) -> list[ParsedBlock]:
        """Parse PPTX returning rich ParsedBlock list."""
        return self._parse_sync(file_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_sync(self, file_path: str) -> list[ParsedBlock]:
        prs = PptxPresentation(file_path)
        blocks: list[ParsedBlock] = []

        # Extract images from the pptx archive (zip)
        image_map = self._extract_images(file_path)

        for slide_num, slide in enumerate(prs.slides, 1):
            slide_blocks = self._parse_slide(slide, slide_num, image_map)
            blocks.extend(slide_blocks)

            # Speaker notes as supplementary content
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    blocks.append(ParsedBlock(
                        content=notes_text,
                        block_type="text",
                        section="",
                        page=slide_num,
                        metadata={
                            "content_type": "speaker_notes",
                            "slide_number": slide_num,
                        },
                    ))

        return blocks

    def _parse_slide(
        self,
        slide,
        slide_num: int,
        image_map: dict[str, bytes],
    ) -> list[ParsedBlock]:
        """Extract blocks from a single slide, sorted by reading order."""
        blocks: list[ParsedBlock] = []
        slide_title = self._find_slide_title(slide)

        for shape in slide.shapes:
            block = self._parse_shape(shape, slide_num, slide_title, image_map)
            if block is not None:
                blocks.append(block)

        return ParsedBlock.sorted_by_position(blocks)

    def _parse_shape(
        self,
        shape: BaseShape,
        slide_num: int,
        slide_title: str,
        image_map: dict[str, bytes],
    ) -> ParsedBlock | None:
        """Parse a single shape into a ParsedBlock (or None if empty/unsupported)."""
        bbox = (
            shape.left or 0,
            shape.top or 0,
            (shape.left or 0) + (shape.width or 0),
            (shape.top or 0) + (shape.height or 0),
        )

        # ---- Table shape ----
        if shape.has_table:
            table = shape.table
            md = self._table_to_markdown(table)
            if md and md.strip():
                return ParsedBlock(
                    content=md.strip(),
                    block_type="table",
                    section=slide_title,
                    page=slide_num,
                    bbox=bbox,
                    metadata={
                        "content_type": "table",
                        "shape_name": shape.name,
                    },
                )

        # ---- Picture shape ----
        if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
            rId = self._get_image_rId(shape)
            img_data = image_map.get(rId) if rId else None
            if img_data:
                return ParsedBlock(
                    content="",  # to be filled by vision LLM
                    block_type="image",
                    section=slide_title,
                    page=slide_num,
                    bbox=bbox,
                    image_base64=base64.b64encode(img_data).decode("ascii"),
                    metadata={
                        "content_type": "image",
                        "img_format": "png",
                        "shape_name": shape.name,
                        "slide_number": slide_num,
                    },
                )

        # ---- Text shape ----
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if not text:
                return None

            # Determine if this is a title or body text
            is_title = (text == slide_title)
            return ParsedBlock(
                content=text,
                block_type="text",
                section=slide_title if not is_title else "",
                page=slide_num,
                bbox=bbox,
                metadata={
                    "content_type": "title" if is_title else "paragraph",
                    "shape_name": shape.name,
                    "slide_number": slide_num,
                },
            )

        return None

    # ------------------------------------------------------------------
    # Slide title detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_slide_title(slide) -> str:
        """Find the title text from a slide's title placeholder or largest text."""
        for shape in slide.shapes:
            if shape.is_placeholder and shape.placeholder_format.idx == 0:
                if shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if text:
                        return text

        # Fallback: find the shape with the most text at the top of the slide
        candidates: list[tuple[float, str]] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if text and len(text) > 5:
                    candidates.append((shape.top or 0, text))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            top_text = candidates[0][1]
            # Use as title if short enough
            if len(top_text) <= 100:
                return top_text

        return ""

    # ------------------------------------------------------------------
    # Image extraction from pptx archive
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_images(file_path: str) -> dict[str, bytes]:
        """Build a map from rId → image bytes from the pptx archive.

        Uses ``ppt/_rels/presentation.xml.rels`` to resolve rId → media path,
        plus per-slide rels for images embedded in individual slides.
        """
        image_map: dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                import xml.etree.ElementTree as ET

                ns = {
                    "r": "http://schemas.openxmlformats.org/package/2006/relationships",
                }

                # 1. Global presentation rels
                rel_files = ["ppt/_rels/presentation.xml.rels"]

                # 2. Per-slide rels (slide1.xml.rels, slide2.xml.rels, ...)
                slide_rel_pattern = re.compile(r"ppt/slides/_rels/slide\d+\.xml\.rels")
                for name in zf.namelist():
                    if slide_rel_pattern.match(name):
                        rel_files.append(name)

                # 3. Parse all rels files
                for rel_path in rel_files:
                    try:
                        rels_xml = zf.read(rel_path)
                        root = ET.fromstring(rels_xml)

                        for rel in root.findall(".//r:Relationship", ns):
                            rId = rel.get("Id", "")
                            target = rel.get("Target", "")
                            rel_type = rel.get("Type", "")

                            if "image" in rel_type.lower() or "media" in target.lower():
                                # Resolve relative path from the rels file location
                                base = rel_path.rsplit("/", 1)[0] if "/" in rel_path else "ppt"
                                media_path = f"{base}/{target}" if not target.startswith("/") else target[1:]

                                # Normalize path
                                media_path = media_path.replace("/./", "/")

                                try:
                                    img_bytes = zf.read(media_path)
                                    if img_bytes:
                                        image_map[rId] = img_bytes
                                except KeyError:
                                    # Try alternative path resolution
                                    alt_path = f"ppt/{target}"
                                    try:
                                        img_bytes = zf.read(alt_path)
                                        image_map[rId] = img_bytes
                                    except KeyError:
                                        continue
                    except Exception:
                        continue
        except Exception:
            pass

        return image_map

    # ------------------------------------------------------------------
    # Image rId extraction from shape XML
    # ------------------------------------------------------------------

    @staticmethod
    def _get_image_rId(shape: BaseShape) -> str:
        """Extract the r:embed rId from a picture shape's XML."""
        try:
            xml = shape._element.xml
            import re as _re
            m = _re.search(r'r:embed="(rId\d+)"', xml)
            return m.group(1) if m else ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Table → Markdown
    # ------------------------------------------------------------------

    @staticmethod
    def _table_to_markdown(table: PptxTable) -> str:
        """Convert a python-pptx Table shape to Markdown."""
        rows = table.rows
        if not rows:
            return ""

        lines: list[str] = []
        for row_idx, row in enumerate(rows):
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
            if row_idx == 0:
                lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

        return "\n".join(lines)
