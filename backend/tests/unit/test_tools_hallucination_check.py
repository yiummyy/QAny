"""Task 7f: hallucination_check tool tests."""

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.tool_registry import TOOL_HANDLERS
from app.tools.hallucination_check import (
    HALLUCINATION_HIGH,
    HALLUCINATION_MEDIUM,
    FALLBACK_ANSWER,
    parse_hallucination_result,
)


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


async def test_hallucination_check_registered():
    from app.tools.hallucination_check import hallucination_check

    assert "hallucination_check" in TOOL_HANDLERS


async def test_hallucination_check_skip_fallback_answer(admin_claims):
    from app.tools.hallucination_check import hallucination_check

    result = await hallucination_check(
        answer=FALLBACK_ANSWER,
        chunks=[],
        user_claims=admin_claims,
    )
    assert result.status == "ok"
    assert result.data["score"] == 1.0
    assert result.data["verdict"] == "high"


async def test_hallucination_check_empty_answer(admin_claims):
    from app.tools.hallucination_check import hallucination_check

    result = await hallucination_check(answer="", chunks=[], user_claims=admin_claims)
    assert result.status == "ok"
    assert result.data["score"] == 1.0


async def test_hallucination_check_returns_prompt(admin_claims):
    from app.tools.hallucination_check import hallucination_check

    chunks = [{"_id": "c1", "content": "参考内容", "doc_name": "test.md"}]
    result = await hallucination_check(answer="测试答案", chunks=chunks, user_claims=admin_claims)
    assert "prompt" in result.data
    assert "测试答案" in result.data["prompt"]


async def test_parse_hallucination_high_score():
    response = '{"score": 0.92, "verdict": "high", "analysis": [{"sentence": "test", "supported": true, "source": "S1"}]}'
    result = parse_hallucination_result(response)
    assert result["score"] == 0.92
    assert result["verdict"] == "high"
    assert result["needs_fallback"] is False


async def test_parse_hallucination_medium_score():
    response = '{"score": 0.7, "verdict": "medium", "analysis": []}'
    result = parse_hallucination_result(response)
    assert result["verdict"] == "medium"
    assert result["needs_fallback"] is False  # 0.7 >= 0.6


async def test_parse_hallucination_low_score_needs_fallback():
    response = '{"score": 0.4, "verdict": "low", "analysis": []}'
    result = parse_hallucination_result(response)
    assert result["verdict"] == "low"
    assert result["needs_fallback"] is True
    assert result["score"] == 0.4


async def test_parse_hallucination_with_markdown_fence():
    response = '```json\n{"score": 0.5, "verdict": "low", "analysis": []}\n```'
    result = parse_hallucination_result(response)
    assert result["score"] == 0.5
    assert result["needs_fallback"] is True


async def test_parse_hallucination_overrides_verdict_by_score():
    """parse_hallucination_result recalculates verdict based on score thresholds."""
    response = '{"score": 0.95, "verdict": "medium", "analysis": []}'
    result = parse_hallucination_result(response)
    assert result["verdict"] == "high"  # overridden by score threshold


def test_hallucination_thresholds():
    assert HALLUCINATION_HIGH == 0.8
    assert HALLUCINATION_MEDIUM == 0.6
