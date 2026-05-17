"""PDF parser — layout-aware extraction via pymupdf.

Capabilities (vs legacy pypdf):
- Text with per-character coordinates → reading-order reconstruction
- Built-in table detection → Markdown table output
- Image extraction → base64 PNG for vision-LLM description
- Font-size-based heading inference (when TOC/bookmarks absent)
- Multi-column page handling
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import fitz  # pymupdf

from app.knowledge.parsers.base import BaseParser
from app.knowledge.parsers.models import ParsedBlock

logger = logging.getLogger(__name__)

# Font size ratio threshold for heading detection.
# Text with font size >= HEADING_FONT_RATIO * median body size is treated as a heading.
HEADING_FONT_RATIO = 1.25
# Minimum font size difference (pt) to consider a heading beyond the ratio.
HEADING_MIN_DELTA = 1.5


class PdfParser(BaseParser):
    """Layout-aware PDF parser using pymupdf."""

    async def parse(self, file_path: str) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        blocks = await loop.run_in_executor(None, self._parse_sync, file_path)
        return [b.to_paragraph_dict() for b in blocks]

    # ------------------------------------------------------------------
    # Public sync entry — returns ParsedBlock for direct use by chunker
    # ------------------------------------------------------------------

    def parse_blocks(self, file_path: str) -> list[ParsedBlock]:
        """Parse PDF returning rich ParsedBlock list (bypasses legacy dict layer)."""
        return self._parse_sync(file_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _parse_sync(self, file_path: str) -> list[ParsedBlock]:
        doc = fitz.open(file_path)
        try:
            # Extract TOC for section hierarchy (may be empty for unstructured PDFs)
            toc_entries = self._parse_toc(doc)

            # Determine median body font size for heading inference
            body_font_size = self._estimate_body_font_size(doc)

            all_blocks: list[ParsedBlock] = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_number = page_num + 1  # 1-based

                page_blocks = self._parse_page(
                    page, page_number, toc_entries, body_font_size
                )
                all_blocks.extend(page_blocks)

            return all_blocks
        finally:
            doc.close()

    def _parse_page(
        self,
        page: fitz.Page,
        page_number: int,
        toc_entries: list[dict],
        body_font_size: float,
    ) -> list[ParsedBlock]:
        """Extract text, table, and image blocks from a single page."""
        blocks: list[ParsedBlock] = []
        page_rect = page.rect

        # ---- Tables (extract first, so we can skip overlapping text) ----
        table_regions: list[fitz.Rect] = []
        try:
            tabs = page.find_tables()
            if tabs and tabs.tables:
                for tab in tabs.tables:
                    md = tab.to_markdown()
                    if md and md.strip():
                        bbox = tab.bbox  # (x0, y0, x1, y1)
                        blocks.append(ParsedBlock(
                            content=md.strip(),
                            block_type="table",
                            section=self._resolve_section(page_number, toc_entries),
                            page=page_number,
                            bbox=bbox,
                            metadata={"content_type": "table"},
                        ))
                        table_regions.append(fitz.Rect(bbox))
        except Exception:
            pass  # table detection is best-effort

        # ---- Images ----
        try:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base_image = page.parent.extract_image(xref)
                except Exception:
                    continue
                if not base_image:
                    continue
                img_bytes = base_image.get("image")
                if not img_bytes:
                    continue

                # Determine image position on page
                img_bbox = self._find_image_bbox(page, img_info)
                if img_bbox is None:
                    img_bbox = (0, 0, page_rect.width, page_rect.height)

                img_format = base_image.get("ext", "png")
                b64 = base64.b64encode(img_bytes).decode("ascii")

                blocks.append(ParsedBlock(
                    content="",  # to be filled by vision LLM
                    block_type="image",
                    section=self._resolve_section(page_number, toc_entries),
                    page=page_number,
                    bbox=img_bbox,
                    image_base64=b64,
                    metadata={
                        "content_type": "image",
                        "img_format": img_format,
                        "img_width": base_image.get("width", 0),
                        "img_height": base_image.get("height", 0),
                    },
                ))
        except Exception:
            pass

        # ---- Text blocks (with reading-order sorting) ----
        text_blocks: list[ParsedBlock] = []
        try:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # type 0 = text
                    continue

                block_bbox = block.get("bbox", (0, 0, 0, 0))
                bbox_rect = fitz.Rect(block_bbox)

                # Skip text that overlaps with detected tables (>60% overlap)
                if any(
                    bbox_rect.intersect(tab_r).get_area() / max(bbox_rect.get_area(), 1)
                    > 0.6
                    for tab_r in table_regions
                ):
                    continue

                # Collect text from lines inside this block
                lines_text = []
                block_font_sizes = []
                for line in block.get("lines", []):
                    line_text = ""
                    for span in line.get("spans", []):
                        line_text += span.get("text", "")
                        span_size = span.get("size", 0)
                        if span_size:
                            block_font_sizes.append(span_size)
                    if line_text.strip():
                        lines_text.append(line_text.strip())

                if not lines_text:
                    continue

                full_text = " ".join(lines_text)

                # Infer if this block is a heading (font-size heuristic)
                avg_font = (
                    sum(block_font_sizes) / len(block_font_sizes)
                    if block_font_sizes
                    else body_font_size
                )
                is_heading = (
                    body_font_size > 0
                    and avg_font >= body_font_size * HEADING_FONT_RATIO
                    and (avg_font - body_font_size) >= HEADING_MIN_DELTA
                )

                section = self._resolve_section(page_number, toc_entries)

                if is_heading:
                    # Heading blocks carry the text as section, not content
                    # They will be used by the chunker to prefix subsequent content
                    text_blocks.append(ParsedBlock(
                        content=full_text,
                        block_type="text",
                        section=section,
                        page=page_number,
                        bbox=block_bbox,
                        metadata={
                            "content_type": "heading",
                            "font_size": round(avg_font, 1),
                        },
                    ))
                else:
                    text_blocks.append(ParsedBlock(
                        content=full_text,
                        block_type="text",
                        section=section,
                        page=page_number,
                        bbox=block_bbox,
                        metadata={"content_type": "paragraph"},
                    ))
        except Exception:
            pass

        # Sort text blocks by reading order then merge with tables/images
        text_blocks = ParsedBlock.sorted_by_position(text_blocks)

        # Post-process: propagate detected headings into subsequent blocks' sections
        text_blocks = self._propagate_headings(text_blocks)

        blocks.extend(text_blocks)

        # Final sort: tables + images + text, all by position
        return ParsedBlock.sorted_by_position(blocks)

    # ------------------------------------------------------------------
    # TOC / Section helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_toc(doc: fitz.Document) -> list[dict]:
        """Extract TOC as list of {level, title, page}."""
        try:
            toc = doc.get_toc(simple=False)
            entries: list[dict] = []
            for item in toc:
                entries.append({
                    "level": item[0],
                    "title": item[1].strip(),
                    "page": item[2],
                })
            return entries
        except Exception:
            return []

    @staticmethod
    def _resolve_section(page_number: int, toc: list[dict]) -> str:
        """Find the deepest TOC entry that starts on or before *page_number*."""
        ancestors: list[str] = []
        for entry in toc:
            if entry["page"] > page_number:
                break
            level = entry["level"]
            title = entry["title"]
            # Maintain stack at correct depth
            while len(ancestors) >= level:
                ancestors.pop()
            ancestors.append(title)
        return " > ".join(ancestors) if ancestors else ""

    # ------------------------------------------------------------------
    # Image position detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_image_bbox(
        page: fitz.Page, img_info: tuple
    ) -> tuple[float, float, float, float] | None:
        """Try to locate the image's position on the page via its xref."""
        xref = img_info[0]
        for img_block in page.get_image_bbox(img_info):
            if img_block[0] == xref:
                return img_block[1]  # (x0, y0, x1, y1)
        return None

    # ------------------------------------------------------------------
    # Font size estimation for heading detection
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_body_font_size(doc: fitz.Document, sample_pages: int = 5) -> float:
        """Sample the first N pages to find the median body font size."""
        sizes: list[float] = []
        pages_to_check = min(sample_pages, len(doc))
        for page_num in range(pages_to_check):
            try:
                page = doc[page_num]
                text_dict = page.get_text("dict")
                for block in text_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            s = span.get("size", 0)
                            if 6 < s < 30:  # plausible body range (6pt–30pt)
                                sizes.append(s)
            except Exception:
                continue

        if not sizes:
            return 10.0  # default

        sizes.sort()
        n = len(sizes)
        # Use median of body-sized fonts
        return sizes[n // 2]

    # ------------------------------------------------------------------
    # Heading propagation
    # ------------------------------------------------------------------

    @staticmethod
    def _propagate_headings(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
        """Detected headings propagate their content into subsequent blocks' sections."""
        current_headings: list[str] = []
        result: list[ParsedBlock] = []

        for block in blocks:
            if block.metadata.get("content_type") == "heading":
                # Replace heading stack — headings at same level pop deeper
                heading_text = block.content
                # Simple heuristic: shorter text = higher-level heading
                level = 1 if len(heading_text) <= 20 else 2
                while len(current_headings) >= level:
                    current_headings.pop()
                current_headings.append(heading_text)
                # Keep heading blocks themselves, mark as heading
                result.append(block)
            else:
                if current_headings:
                    prefix = " > ".join(current_headings)
                    if block.section:
                        block.section = f"{prefix} > {block.section}"
                    else:
                        block.section = prefix
                result.append(block)

        return result
