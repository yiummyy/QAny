"""Task 7b: hybrid_search tool tests."""

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.tool_registry import TOOL_HANDLERS
from app.tools.hybrid_search import RRF_K, _rrf_fuse


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


@pytest.fixture
def guest_claims():
    return UserClaims(sub="g1", username="guest", role=Role.GUEST, pl="L1", jti="jti-g")


async def test_hybrid_search_registered():
    from app.tools.hybrid_search import hybrid_search

    assert "hybrid_search" in TOOL_HANDLERS


def test_rrf_fuse_merges_two_lists():
    list_a = [
        {"_id": "c1", "content": "aaa", "_score": 0.9},
        {"_id": "c2", "content": "bbb", "_score": 0.8},
    ]
    list_b = [
        {"_id": "c2", "content": "bbb", "_score": 0.7},
        {"_id": "c3", "content": "ccc", "_score": 0.6},
    ]
    fused = _rrf_fuse(list_a, list_b, k=60)
    assert len(fused) == 3
    # c2 appears in both lists, should have highest combined score
    assert fused[0]["_id"] == "c2"


def test_rrf_fuse_empty_lists():
    result = _rrf_fuse([], [], k=60)
    assert result == []


def test_rrf_fuse_single_list():
    list_a = [{"_id": "c1", "content": "test", "_score": 0.9}]
    result = _rrf_fuse(list_a, [], k=60)
    assert len(result) == 1
    assert result[0]["_id"] == "c1"


def test_rrf_fuse_preserves_rrf_scores():
    list_a = [{"_id": "c1", "content": "test", "_score": 0.9}]
    list_b = [{"_id": "c1", "content": "test", "_score": 0.8}]
    result = _rrf_fuse(list_a, list_b, k=60)
    assert "_rrf_score" in result[0]
    assert result[0]["_rrf_score"] > 0


def test_rrf_fuse_dedup_by_chunk_id():
    """Chunks with same _id are deduplicated, scores summed."""
    list_a = [{"_id": "same_id", "content": "from_a", "_score": 1.0}]
    list_b = [{"_id": "same_id", "content": "from_b", "_score": 0.5}]
    result = _rrf_fuse(list_a, list_b, k=60)
    assert len(result) == 1
    assert result[0]["content"] == "from_a"  # keeps first occurrence


def test_rrf_k_constant():
    assert RRF_K == 60


def test_build_entity_clauses_generates_multi_match():
    from app.tools.hybrid_search import _build_entity_clauses

    clauses = _build_entity_clauses(["服务器", "宕机"])
    assert len(clauses) == 2
    for clause in clauses:
        assert "multi_match" in clause
        assert "fields" in clause["multi_match"]
        assert "section^3" in clause["multi_match"]["fields"]


def test_build_entity_clauses_empty():
    from app.tools.hybrid_search import _build_entity_clauses

    assert _build_entity_clauses([]) == []
    assert _build_entity_clauses(None) == []
