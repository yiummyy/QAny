"""Task 7e: generate_answer tool tests."""

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.tool_registry import TOOL_HANDLERS


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


async def test_generate_answer_registered():
    from app.tools.generate_answer import generate_answer

    assert "generate_answer" in TOOL_HANDLERS


async def test_generate_answer_returns_prompt(admin_claims):
    from app.tools.generate_answer import generate_answer

    chunks = [{"_id": "c1", "content": "年假为5天", "rerank_score": 0.9, "doc_name": "员工手册.md"}]
    result = await generate_answer(query="年假几天？", chunks=chunks, user_claims=admin_claims)
    assert result.status == "ok"
    assert "prompt" in result.data
    assert "[S1]" in result.data["prompt"]
    assert "年假" in result.data["prompt"]


async def test_generate_answer_fallback_on_low_scores(admin_claims):
    from app.tools.generate_answer import FALLBACK_ANSWER, generate_answer

    chunks = [
        {"_id": "c1", "content": "irrelevant", "rerank_score": 0.1},
        {"_id": "c2", "content": "also irrelevant", "rerank_score": 0.05},
    ]
    result = await generate_answer(query="test", chunks=chunks, user_claims=admin_claims)
    assert result.status == "degraded"
    assert result.data["answer"] == FALLBACK_ANSWER
    assert result.data["sources"] == []


async def test_generate_answer_empty_chunks(admin_claims):
    from app.tools.generate_answer import generate_answer

    result = await generate_answer(query="test", chunks=[], user_claims=admin_claims)
    assert result.status == "degraded"
    assert "未找到" in result.summary


async def test_generate_answer_formats_chunks_with_index(admin_claims):
    from app.tools.generate_answer import generate_answer

    chunks = [
        {"_id": "c1", "content": "第一条信息", "rerank_score": 0.8, "doc_name": "doc1.md"},
        {"_id": "c2", "content": "第二条信息", "rerank_score": 0.7, "doc_name": "doc2.md"},
    ]
    result = await generate_answer(query="查询", chunks=chunks, user_claims=admin_claims)
    assert "[S1]" in result.data["prompt"]
    assert "[S2]" in result.data["prompt"]
    assert "doc1.md" in result.data["prompt"]


async def test_generate_answer_permission_note_for_guest():
    guest = UserClaims(sub="g1", username="guest", role=Role.GUEST, pl="L1", jti="jti-g")
    from app.tools.generate_answer import generate_answer

    chunks = [{"_id": "c1", "content": "测试内容", "rerank_score": 0.9, "doc_name": "doc.md"}]
    result = await generate_answer(query="test", chunks=chunks, user_claims=guest)
    assert "访客" in result.data["prompt"]
