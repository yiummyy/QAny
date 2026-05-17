import pytest

from app.knowledge.chunker import Chunk, chunk_text, estimate_token_count


def test_empty_paragraphs():
    assert chunk_text([]) == []


def test_single_short_paragraph():
    chunks = chunk_text([{"text": "Hello world"}])
    assert len(chunks) == 1
    assert chunks[0].content == "Hello world"
    assert chunks[0].index == 0
    assert chunks[0].content_hash


def test_chinese_token_estimation():
    # Chinese text: ~1.5 chars per token
    tokens = estimate_token_count("你好世界")
    assert tokens > 0
    # 4 Chinese chars / 1.5 ≈ 2.67 → int → 2
    assert tokens >= 2


def test_english_token_estimation():
    # English text: ~4 chars per token
    tokens = estimate_token_count("hello")
    # 5 chars / 4.0 = 1.25 → int → 1
    assert tokens >= 1


def test_mixed_cn_en_estimation():
    tokens = estimate_token_count("hello世界")
    # "hello"=5/4=1.25, "世界"=2/1.5=1.33 → total≈2
    assert tokens >= 2


def test_paragraph_boundary_preserved():
    """Sentences from the same paragraph should be kept together."""
    text = [{"text": "第一段。第二句。", "section": "§1"}]
    chunks = chunk_text(text, chunk_size=9999, overlap=0)
    assert len(chunks) == 1
    assert "第一段" in chunks[0].content
    assert "第二句" in chunks[0].content


def test_large_text_multiple_chunks():
    """Large text should produce multiple chunks."""
    paragraphs = []
    for i in range(50):
        text = f"这是第{i}段内容。" * 10
        paragraphs.append({"text": text, "section": f"§{i}"})
    chunks = chunk_text(paragraphs, chunk_size=512, overlap=128)
    assert len(chunks) > 1


def test_chunk_indices_sequential():
    paragraphs = [{"text": f"段落{i}的内容" * 30} for i in range(20)]
    chunks = chunk_text(paragraphs, chunk_size=512, overlap=128)
    for i, c in enumerate(chunks):
        assert c.index == i


def test_section_info_preserved():
    paragraphs = [
        {"text": "第一章内容。", "section": "第一章"},
        {"text": "第二章内容。", "section": "第二章"},
    ]
    chunks = chunk_text(paragraphs, chunk_size=9999, overlap=0)
    assert len(chunks) == 1
    assert "第一章" in chunks[0].section or "第二章" in chunks[0].section


def test_content_hash_stable():
    chunk1 = Chunk(index=0, content="test")
    chunk2 = Chunk(index=0, content="test")
    assert chunk1.content_hash == chunk2.content_hash


def test_content_hash_different():
    chunk1 = Chunk(index=0, content="test1")
    chunk2 = Chunk(index=0, content="test2")
    assert chunk1.content_hash != chunk2.content_hash


def test_very_long_sentence():
    """A single very long sentence should still be chunkable."""
    long_text = "这是一个很长的句子" * 200
    chunks = chunk_text([{"text": long_text}], chunk_size=512, overlap=128)
    assert len(chunks) > 0
    for c in chunks:
        assert len(c.content) > 0


@pytest.mark.parametrize("chunk_size,overlap", [
    (256, 64),
    (512, 128),
    (1024, 256),
])
def test_different_chunk_sizes(chunk_size, overlap):
    paragraphs = [{"text": f"段落{i}的内容" * 30} for i in range(10)]
    chunks = chunk_text(paragraphs, chunk_size=chunk_size, overlap=overlap)
    assert len(chunks) > 0
