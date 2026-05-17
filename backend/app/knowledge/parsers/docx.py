"""DOCX parser — heading-aware text + table + image extraction.

Enhanced from the legacy implementation with:
- Table detection → Markdown conversion
- Inline image extraction → base64 PNG for vision-LLM description
- Structured section hierarchy from Heading styles
"""

from __future__ import annotations

import asyncio
import base64
import logging
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from app.knowledge.parsers.base import BaseParser
from app.knowledge.parsers.models import ParsedBlock

logger = logging.getLogger(__name__)

# docx namespace for inline images
_DOCX_NS = {
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


class DocxParser(BaseParser):
    """Heading-aware DOCX parser with table and image extraction."""

    async def parse(self, file_path: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        blocks = await loop.run_in_executor(None, self._parse_sync, file_path)
        return [b.to_paragraph_dict() for b in blocks]

    def parse_blocks(self, file_path: str) -> list[ParsedBlock]:
        """Parse DOCX returning rich ParsedBlock list."""
        return self._parse_sync(file_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_sync(self, file_path: str) -> list[ParsedBlock]:
        doc = DocxDocument(file_path)
        blocks: list[ParsedBlock] = []

        # Extract images from the docx archive (zip)
        image_map = self._extract_images(file_path)

        section_stack: list[str] = []
        para_index = 0

        for para in doc.paragraphs:
            para_index += 1

            # ---- Style-based heading detection ----
            style_name = para.style.name if para.style else ""
            if style_name and style_name.startswith("Heading"):
                level = self._heading_level(style_name)
                heading_text = para.text.strip()
                if not heading_text:
                    continue
                while len(section_stack) >= level:
                    section_stack.pop()
                section_stack.append(heading_text)

                # Emit heading as a block so chunker can use it
                blocks.append(ParsedBlock(
                    content=heading_text,
                    block_type="text",
                    section=" > ".join(section_stack[:-1]) if len(section_stack) > 1 else "",
                    page=0,
                    metadata={
                        "content_type": "heading",
                        "heading_level": level,
                    },
                ))
                continue

            text = para.text.strip()
            section = " > ".join(section_stack) if section_stack else ""

            # ---- Inline image detection ----
            images_in_para = self._find_inline_images(para)
            for img_rId in images_in_para:
                img_data = image_map.get(img_rId)
                if img_data:
                    blocks.append(ParsedBlock(
                        content="",  # to be filled by vision LLM
                        block_type="image",
                        section=section,
                        page=0,
                        image_base64=base64.b64encode(img_data).decode("ascii"),
                        metadata={
                            "content_type": "image",
                            "img_format": "png",
                            "paragraph_index": para_index,
                        },
                    ))

            if not text:
                continue

            blocks.append(ParsedBlock(
                content=text,
                block_type="text",
                section=section,
                page=0,
                metadata={"content_type": "paragraph"},
            ))

        # ---- Tables ----
        for table_index, table in enumerate(doc.tables):
            md = self._table_to_markdown(table)
            if md and md.strip():
                blocks.append(ParsedBlock(
                    content=md.strip(),
                    block_type="table",
                    section=section_stack[-1] if section_stack else "",
                    page=0,
                    metadata={
                        "content_type": "table",
                        "table_index": table_index,
                    },
                ))

        return blocks

    # ------------------------------------------------------------------
    # Image extraction from docx zip
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_images(file_path: str) -> dict[str, bytes]:
        """Build a map from rId → image bytes by reading the docx archive.

        Relationships are in ``word/_rels/document.xml.rels``; media files
        live under ``word/media/``.
        """
        image_map: dict[str, bytes] = {}
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                # Parse relationships to map rId → media path
                rels_path = "word/_rels/document.xml.rels"
                if rels_path not in zf.namelist():
                    return image_map

                import xml.etree.ElementTree as ET
                rels_xml = zf.read(rels_path)
                root = ET.fromstring(rels_xml)

                ns = {
                    "r": "http://schemas.openxmlformats.org/package/2006/relationships",
                }

                rId_to_path: dict[str, str] = {}
                for rel in root.findall(".//r:Relationship", ns):
                    rId = rel.get("Id", "")
                    target = rel.get("Target", "")
                    rel_type = rel.get("Type", "")
                    if "image" in rel_type.lower() or "media" in target.lower():
                        # Resolve relative path
                        media_path = "word/" + target
                        rId_to_path[rId] = media_path

                # Read image bytes
                for rId, media_path in rId_to_path.items():
                    try:
                        img_bytes = zf.read(media_path)
                        image_map[rId] = img_bytes
                    except KeyError:
                        continue
        except Exception:
            pass

        return image_map

    # ------------------------------------------------------------------
    # Inline image detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_inline_images(para) -> list[str]:
        """Find image relationship IDs embedded in a paragraph's XML."""
        rIds: list[str] = []
        try:
            xml = para._element.xml
            import re
            # Match r:embed="rIdX" inside drawing elements
            matches = re.findall(r'r:embed="(rId\d+)"', xml)
            rIds.extend(matches)
        except Exception:
            pass
        return rIds

    # ------------------------------------------------------------------
    # Table → Markdown
    # ------------------------------------------------------------------

    @staticmethod
    def _table_to_markdown(table) -> str:
        """Convert a python-docx Table to a Markdown table string."""
        rows = table.rows
        if not rows:
            return ""

        lines: list[str] = []
        for row_idx, row in enumerate(rows):
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            lines.append("| " + " | ".join(cells) + " |")
            if row_idx == 0:
                # Header separator
                lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Heading level parser
    # ------------------------------------------------------------------

    @staticmethod
    def _heading_level(style_name: str) -> int:
        """Extract heading level from style name (e.g. 'Heading 1' → 1)."""
        import re
        m = re.search(r"(\d+)", style_name)
        return int(m.group(1)) if m else 1
