from app.knowledge.parsers.base import BaseParser
from app.knowledge.parsers.docx import DocxParser
from app.knowledge.parsers.md import MarkdownParser
from app.knowledge.parsers.models import ParsedBlock
from app.knowledge.parsers.pdf import PdfParser
from app.knowledge.parsers.pptx import PptxParser
from app.knowledge.parsers.txt import TxtParser
from app.knowledge.parsers.vision import describe_images, describe_images_sync

PARSERS: dict[str, BaseParser] = {
    ".pdf": PdfParser(),
    ".docx": DocxParser(),
    ".pptx": PptxParser(),
    ".md": MarkdownParser(),
    ".txt": TxtParser(),
}

# Parsers that support layout-aware parsing (return rich ParsedBlock).
# The *parse_blocks()* method on these returns list[ParsedBlock] instead
# of list[dict], enabling table/image/heading metadata downstream.
LAYOUT_AWARE_PARSERS: dict[str, PdfParser | DocxParser | PptxParser] = {
    ".pdf": PARSERS[".pdf"],   # type: ignore[dict-item]
    ".docx": PARSERS[".docx"],  # type: ignore[dict-item]
    ".pptx": PARSERS[".pptx"],  # type: ignore[dict-item]
}


def get_parser(extension: str) -> BaseParser | None:
    """Return a parser for the given file extension.

    Supports ``.pdf``, ``.docx``, ``.md``, ``.txt``.
    """
    return PARSERS.get(extension.lower())


def get_layout_parser(extension: str) -> PdfParser | DocxParser | None:
    """Return a layout-aware parser for rich block extraction.

    Only PDF and DOCX support layout features (tables, images, headings).
    Text-based formats (Markdown, TXT) go through the standard BaseParser.
    """
    return LAYOUT_AWARE_PARSERS.get(extension.lower())


__all__ = [
    "BaseParser",
    "DocxParser",
    "MarkdownParser",
    "ParsedBlock",
    "PdfParser",
    "PptxParser",
    "TxtParser",
    "describe_images",
    "describe_images_sync",
    "get_parser",
    "get_layout_parser",
    "PARSERS",
    "LAYOUT_AWARE_PARSERS",
]
