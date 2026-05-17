import pytest

from app.knowledge.parsers import PARSERS, get_parser
from app.knowledge.parsers.docx import DocxParser
from app.knowledge.parsers.md import MarkdownParser
from app.knowledge.parsers.pdf import PdfParser
from app.knowledge.parsers.pptx import PptxParser
from app.knowledge.parsers.txt import TxtParser


def test_parser_registry():
    assert ".pdf" in PARSERS
    assert ".docx" in PARSERS
    assert ".pptx" in PARSERS
    assert ".md" in PARSERS
    assert ".txt" in PARSERS
    assert isinstance(PARSERS[".pdf"], PdfParser)
    assert isinstance(PARSERS[".docx"], DocxParser)
    assert isinstance(PARSERS[".pptx"], PptxParser)
    assert isinstance(PARSERS[".md"], MarkdownParser)
    assert isinstance(PARSERS[".txt"], TxtParser)


@pytest.mark.parametrize("ext,expected", [
    (".pdf", PdfParser),
    (".PDF", PdfParser),
    (".docx", DocxParser),
    (".DOCX", DocxParser),
    (".pptx", PptxParser),
    (".PPTX", PptxParser),
    (".md", MarkdownParser),
    (".txt", TxtParser),
    ("", None),
])
def test_get_parser(ext, expected):
    p = get_parser(ext)
    if expected is None:
        assert p is None
    else:
        assert isinstance(p, expected)
