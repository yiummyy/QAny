"""Tests for type-aware chunker (chunk_blocks) and ParsedBlock model."""

import pytest

from app.knowledge.chunker import Chunk, chunk_blocks, chunk_text
from app.knowledge.parsers.models import ParsedBlock


# ── ParsedBlock ──────────────────────────────────────────────────


def test_parsed_block_to_dict_text():
    b = ParsedBlock(content="Hello", block_type="text", section="Ch1", page=1)
    d = b.to_paragraph_dict()
    assert d["text"] == "Hello"
    assert d["section"] == "Ch1"
    assert d["page"] == 1
    assert "block_type" not in d  # text is default, omitted


def test_parsed_block_to_dict_table():
    b = ParsedBlock(content="| A | B |", block_type="table", section="T1", page=2)
    d = b.to_paragraph_dict()
    assert d["block_type"] == "table"
    assert d["text"] == "| A | B |"


def test_parsed_block_to_dict_image():
    b = ParsedBlock(
        content="chart description",
        block_type="image",
        section="S1",
        page=3,
        metadata={"content_type": "image_description"},
    )
    d = b.to_paragraph_dict()
    assert d["block_type"] == "image"
    assert "image_description" in str(d["metadata"])


def test_sorted_by_position():
    b1 = ParsedBlock(content="Top", page=1, bbox=(0, 0, 100, 50))
    b2 = ParsedBlock(content="Bottom", page=1, bbox=(0, 60, 100, 110))
    b3 = ParsedBlock(content="Page2", page=2, bbox=(0, 0, 100, 50))
    sorted_blocks = ParsedBlock.sorted_by_position([b2, b3, b1])
    assert [b.content for b in sorted_blocks] == ["Top", "Bottom", "Page2"]


def test_sorted_by_position_same_y():
    b1 = ParsedBlock(content="Left", page=1, bbox=(0, 10, 50, 60))
    b2 = ParsedBlock(content="Right", page=1, bbox=(60, 10, 110, 60))
    sorted_blocks = ParsedBlock.sorted_by_position([b2, b1])
    assert [b.content for b in sorted_blocks] == ["Left", "Right"]


# ── chunk_blocks: basic text ─────────────────────────────────────


def test_chunk_blocks_empty():
    assert chunk_blocks([]) == []


def test_chunk_blocks_simple_text():
    blocks = [ParsedBlock(content="Hello world.", block_type="text", page=1)]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 1
    assert chunks[0].content == "Hello world."
    assert chunks[0].content_type == "text"
    assert chunks[0].page == 1


def test_chunk_blocks_text_respects_boundaries():
    blocks = [ParsedBlock(content="第一句。第二句。第三句。", block_type="text")]
    chunks = chunk_blocks(blocks, chunk_size=9999, overlap=0)
    assert len(chunks) == 1
    assert "第一句" in chunks[0].content


# ── chunk_blocks: tables ─────────────────────────────────────────


def test_chunk_blocks_table_intact():
    """Tables should stay as single chunks, not split into sentences."""
    table_content = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob | 25 |"
    blocks = [
        ParsedBlock(content=table_content, block_type="table", section="Data", page=2),
    ]
    chunks = chunk_blocks(blocks)
    table_chunks = [c for c in chunks if c.content_type == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0].content == table_content
    assert table_chunks[0].page == 2
    assert table_chunks[0].section == "Data"


def test_chunk_blocks_large_table_truncated():
    """Very large tables should be truncated, not split."""
    huge_table = "| Col |\n|-----|\n" + "\n".join(f"| {i} |" for i in range(2000))
    blocks = [ParsedBlock(content=huge_table, block_type="table")]
    chunks = chunk_blocks(blocks)
    table_chunks = [c for c in chunks if c.content_type == "table"]
    assert len(table_chunks) == 1
    assert table_chunks[0].metadata.get("truncated") is True
    assert "已截断" in table_chunks[0].content


def test_chunk_blocks_table_with_text():
    """Table plus adjacent text → table chunk + text chunk."""
    blocks = [
        ParsedBlock(content="| A | B |\n| 1 | 2 |", block_type="table", page=2),
        ParsedBlock(content="After text。", block_type="text", page=2),
    ]
    chunks = chunk_blocks(blocks)
    types = [c.content_type for c in chunks]
    assert "table" in types
    assert "text" in types


# ── chunk_blocks: images ─────────────────────────────────────────


def test_chunk_blocks_image_standalone():
    blocks = [
        ParsedBlock(content="柱状图描述文本", block_type="image", section="S2", page=3),
    ]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 1
    assert chunks[0].content_type == "image_description"
    assert "柱状图描述文本" in chunks[0].content


def test_chunk_blocks_empty_image_placeholder():
    """Image blocks with empty content get a placeholder."""
    blocks = [ParsedBlock(content="", block_type="image", page=3)]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 1
    assert chunks[0].content_type == "image_description"
    assert len(chunks[0].content) > 0  # has placeholder


# ── chunk_blocks: headings ───────────────────────────────────────


def test_chunk_blocks_heading_propagation():
    """Heading blocks should propagate into subsequent content sections."""
    blocks = [
        ParsedBlock(
            content="第一章 概述",
            block_type="text",
            metadata={"content_type": "heading", "heading_level": 1},
        ),
        ParsedBlock(
            content="这是正文内容。",
            block_type="text",
            metadata={"content_type": "paragraph"},
        ),
    ]
    chunks = chunk_blocks(blocks)
    heading_chunks = [c for c in chunks if c.metadata.get("content_type") == "heading"]
    assert len(heading_chunks) == 1
    assert heading_chunks[0].content == "第一章 概述"


def test_chunk_blocks_heading_multilevel():
    """Nested headings should build proper hierarchy."""
    blocks = [
        ParsedBlock(content="第一章", block_type="text",
                    metadata={"content_type": "heading", "heading_level": 1}),
        ParsedBlock(content="1.1 背景", block_type="text",
                    metadata={"content_type": "heading", "heading_level": 2}),
        ParsedBlock(content="Content here。", block_type="text",
                    metadata={"content_type": "paragraph"}),
    ]
    chunks = chunk_blocks(blocks)
    # Find the content chunk
    content_chunks = [c for c in chunks if c.metadata.get("content_type") != "heading"]
    assert len(content_chunks) >= 1


# ── chunk_blocks: content_type propagation ───────────────────────


def test_chunk_blocks_content_type_in_index():
    """Chunk.content_type should flow through to ES index via indexer metadata."""
    blocks = [
        ParsedBlock(content="| Table |\n| Data |", block_type="table"),
        ParsedBlock(content="Image desc", block_type="image"),
        ParsedBlock(content="Plain text。", block_type="text"),
    ]
    chunks = chunk_blocks(blocks)
    assert any(c.content_type == "table" for c in chunks)
    assert any(c.content_type == "image_description" for c in chunks)
    assert any(c.content_type == "text" for c in chunks)


# ── Backward compatibility: chunk_text still works ────────────────


def test_chunk_text_backward_compat():
    """Legacy chunk_text with dict input should still work unchanged."""
    chunks = chunk_text([{"text": "Hello world. Second sentence.", "section": "§1"}])
    assert len(chunks) > 0
    assert chunks[0].content_type == "text"
    assert chunks[0].section == "§1"


def test_chunk_text_with_block_type():
    """Legacy path should pass block_type through to content_type."""
    chunks = chunk_text([
        {"text": "Table content", "section": "", "block_type": "table"}
    ])
    assert len(chunks) == 1
    assert chunks[0].content_type == "table"


# ── Edge cases ───────────────────────────────────────────────────


def test_chunk_blocks_mixed_without_text():
    """Table + image only, no text blocks."""
    blocks = [
        ParsedBlock(content="| A | B |", block_type="table"),
        ParsedBlock(content="Image description", block_type="image"),
    ]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 2
