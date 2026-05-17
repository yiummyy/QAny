import hashlib

from app.knowledge.indexer import make_chunk_id


def test_make_chunk_id_deterministic():
    """Same inputs should produce the same chunk_id."""
    id1 = make_chunk_id("doc_1", 3, "abc123")
    id2 = make_chunk_id("doc_1", 3, "abc123")
    assert id1 == id2


def test_make_chunk_id_different_doc():
    id1 = make_chunk_id("doc_1", 0, "abc")
    id2 = make_chunk_id("doc_2", 0, "abc")
    assert id1 != id2


def test_make_chunk_id_different_index():
    id1 = make_chunk_id("doc_1", 0, "abc")
    id2 = make_chunk_id("doc_1", 1, "abc")
    assert id1 != id2


def test_make_chunk_id_different_hash():
    id1 = make_chunk_id("doc_1", 0, "abc")
    id2 = make_chunk_id("doc_1", 0, "def")
    assert id1 != id2


def test_make_chunk_id_format():
    """chunk_id should be a 32-char hex string (MD5)."""
    cid = make_chunk_id("doc", 0, "hash")
    assert len(cid) == 32
    # Should be valid hex
    int(cid, 16)


def test_make_chunk_id_matches_standalone_md5():
    doc_id = "test_doc"
    idx = 5
    content_hash = "deadbeef"
    cid = make_chunk_id(doc_id, idx, content_hash)
    expected = hashlib.md5(
        f"{doc_id}|{idx}|{content_hash}".encode(), usedforsecurity=False
    ).hexdigest()
    assert cid == expected
