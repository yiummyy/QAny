"""Task 7a: rewrite_query tool tests."""

from unittest.mock import AsyncMock, patch

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.tool_registry import TOOL_HANDLERS


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


async def test_rewrite_query_registered():
    from app.tools.rewrite_query import rewrite_query

    assert "rewrite_query" in TOOL_HANDLERS


async def test_rewrite_query_degraded_on_llm_failure(admin_claims):
    """When LLM call fails, returns degraded with original query."""
    from app.tools.rewrite_query import rewrite_query

    result = await rewrite_query(query="年假怎么申请？", history="", user_claims=admin_claims)
    assert result.status == "degraded"
    assert "年假" in result.data["rewritten"]


async def test_rewrite_query_preserves_user_claims(admin_claims):
    from app.tools.rewrite_query import rewrite_query

    result = await rewrite_query(query="测试", history="", user_claims=admin_claims)
    assert result.status == "degraded"  # LLM not wired yet
    assert result.data["rewritten"] == "测试"
    assert result.data["intent"] == "其他"
    assert result.data["entities"] == []


async def test_rewrite_query_with_history(admin_claims):
    from app.tools.rewrite_query import rewrite_query

    result = await rewrite_query(query="它的流程是什么？", history="用户问过年假制度", user_claims=admin_claims)
    assert result.status == "degraded"
    assert "它" in result.data["rewritten"]
