"""Task 7c: rerank tool tests."""

from unittest.mock import AsyncMock, patch

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import TOOL_HANDLERS


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


async def test_rerank_registered():
    from app.tools.rerank import rerank_chunks

    assert "rerank" in TOOL_HANDLERS


async def test_rerank_empty_chunks(admin_claims):
    from app.tools.rerank import rerank_chunks

    result = await rerank_chunks(query="test", chunks=[], user_claims=admin_claims)
    assert result.status == "ok"
    assert result.data["chunks"] == []


async def test_rerank_degraded_on_error(admin_claims):
    """When reranker fails, returns unranked top_k chunks (degraded)."""
    from app.tools.rerank import rerank_chunks

    chunks = [
        {"_id": "c1", "content": "a"},
        {"_id": "c2", "content": "b"},
        {"_id": "c3", "content": "c"},
        {"_id": "c4", "content": "d"},
        {"_id": "c5", "content": "e"},
        {"_id": "c6", "content": "f"},
    ]
    with patch("app.tools.rerank._rerank", side_effect=RuntimeError("model not loaded")):
        result = await rerank_chunks(query="test", chunks=chunks, top_k=3, user_claims=admin_claims)
    assert result.status == "degraded"
    assert len(result.data["chunks"]) == 3


async def test_rerank_returns_tool_result_type(admin_claims):
    from app.tools.rerank import rerank_chunks

    result = await rerank_chunks(query="test", chunks=[], user_claims=admin_claims)
    assert isinstance(result, ToolResult)
