"""Tests for search_knowledge tool + entity-aware index routing."""

import pytest

from app.tools.search_knowledge import (
    ENTITY_INDEX_HINTS,
    INTENT_INDEX_BOOST,
    _route_indexes,
)

AVAILABLE = ["qa_chunks", "ticket_knowledge", "sales_knowledge", "ops_knowledge"]


class TestIndexRouting:
    """Unit tests for _route_indexes — no I/O, pure logic."""

    def test_fault_with_device_entity_routes_to_ops_and_ticket(self):
        indexes = _route_indexes("故障排查", ["逆变器", "E001"], "qa_chunks", AVAILABLE)
        assert "ops_knowledge" in indexes
        assert "ticket_knowledge" in indexes
        assert "qa_chunks" in indexes  # always include default
        assert len(indexes) >= 2

    def test_fault_intent_boosts_ticket_even_without_device_entity(self):
        indexes = _route_indexes("故障排查", [], "qa_chunks", AVAILABLE)
        assert "ticket_knowledge" in indexes
        assert "qa_chunks" in indexes

    def test_marketing_entity_routes_to_sales(self):
        indexes = _route_indexes("产品知识", ["小红书", "流量"], "qa_chunks", AVAILABLE)
        assert "sales_knowledge" in indexes
        assert "qa_chunks" in indexes

    def test_oa_entity_routes_to_ticket(self):
        indexes = _route_indexes("流程咨询", ["OA", "报销"], "qa_chunks", AVAILABLE)
        assert "ticket_knowledge" in indexes

    def test_error_code_entity_routes_to_ops_and_ticket(self):
        indexes = _route_indexes("故障排查", ["E005"], "qa_chunks", AVAILABLE)
        assert "ops_knowledge" in indexes
        assert "ticket_knowledge" in indexes

    def test_general_question_uses_default_only(self):
        indexes = _route_indexes("制度查询", [], "qa_chunks", AVAILABLE)
        assert indexes == ["qa_chunks"]

    def test_general_question_empty_entities_uses_default_only(self):
        indexes = _route_indexes("其他", [], "qa_chunks", AVAILABLE)
        assert indexes == ["qa_chunks"]

    def test_entity_filtered_by_available(self):
        limited = ["qa_chunks"]  # only qa_chunks available
        indexes = _route_indexes("故障排查", ["逆变器"], "qa_chunks", limited)
        assert "ops_knowledge" not in indexes
        assert indexes == ["qa_chunks"]

    def test_dedup_preserves_order(self):
        # entity matches both ops AND the error_code pattern
        indexes = _route_indexes("故障排查", ["逆变器", "E001"], "qa_chunks", AVAILABLE)
        # ops_knowledge should appear only once
        assert indexes.count("ops_knowledge") == 1

    def test_router_always_includes_default_index(self):
        indexes = _route_indexes("营销", ["报价", "客户"], "qa_chunks", AVAILABLE)
        assert "qa_chunks" in indexes

    def test_empty_available_returns_default(self):
        indexes = _route_indexes("故障排查", ["逆变器"], "qa_chunks", [])
        assert indexes == ["qa_chunks"]


class TestSearchKnowledgeTool:
    """Integration-style tests for the search_knowledge async function."""

    async def test_registered_as_shared_tool(self):
        from app.harness.tool_registry import SHARED_TOOLS
        # Trigger registration by importing the module
        from app.tools.search_knowledge import search_knowledge  # noqa: F401
        assert "search_knowledge" in SHARED_TOOLS

    async def test_returns_degraded_when_search_fails(
        self, admin_claims, agent_config_for_test
    ):
        """When hybrid_search returns error, search_knowledge degrades gracefully."""
        from unittest.mock import AsyncMock, patch
        from app.tools.search_knowledge import search_knowledge

        with patch(
            "app.tools.hybrid_search.hybrid_search",
            new_callable=AsyncMock,
        ) as mock_search:
            from app.harness.models import ToolResult
            mock_search.return_value = ToolResult(
                status="error", summary="ES不可达", data={"chunks": []}
            )

            result = await search_knowledge(
                query="测试问题",
                user_claims=admin_claims,
                agent_config=agent_config_for_test,
                provider_router=None,  # skip rewrite
            )

            assert result.status == "degraded"
            assert result.data["chunks"] == []

    async def test_returns_chunks_with_diagnostics(
        self, admin_claims, agent_config_for_test
    ):
        """Successful search returns chunks and diagnostic metadata."""
        from unittest.mock import AsyncMock, patch
        from app.tools.search_knowledge import search_knowledge

        mock_chunks = [
            {
                "_id": "c1", "chunk_id": "c1",
                "content": "逆变器故障排查步骤",
                "doc_name": "运维手册", "rerank_score": 0.85,
                "permission_level": "L2",
            }
        ]

        with patch(
            "app.tools.hybrid_search.hybrid_search",
            new_callable=AsyncMock,
        ) as mock_search:
            from app.harness.models import ToolResult
            mock_search.return_value = ToolResult(
                status="ok", summary="召回1条", data={"chunks": mock_chunks}
            )

            result = await search_knowledge(
                query="逆变器故障",
                user_claims=admin_claims,
                agent_config=agent_config_for_test,
                provider_router=None,
            )

            assert result.status in ("ok", "degraded")
            diag = result.data.get("diagnostics", {})
            assert "raw_hit_count" in diag
            assert "rerank_top_score" in diag
            assert "permission_filtered" in diag
            assert "indexes_used" in diag

    async def test_explicit_index_override(self, admin_claims, agent_config_for_test):
        """When index is explicitly passed, it overrides automatic routing."""
        from unittest.mock import AsyncMock, patch
        from app.tools.search_knowledge import search_knowledge

        mock_chunks = [
            {
                "_id": "c2", "chunk_id": "c2",
                "content": "测试内容", "doc_name": "测试文档",
                "permission_level": "L1",
            }
        ]

        with patch(
            "app.tools.hybrid_search.hybrid_search",
            new_callable=AsyncMock,
        ) as mock_search:
            from app.harness.models import ToolResult
            mock_search.return_value = ToolResult(
                status="ok", summary="ok", data={"chunks": mock_chunks}
            )

            await search_knowledge(
                query="测试",
                user_claims=admin_claims,
                agent_config=agent_config_for_test,
                provider_router=None,
                index="ticket_knowledge",
            )

            call_kwargs = mock_search.call_args
            assert call_kwargs is not None
            # index parameter should be the explicit override
            called_index = call_kwargs[1].get("index")
            assert called_index == "ticket_knowledge"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_claims():
    from app.auth.claims import Role, UserClaims
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


@pytest.fixture
def agent_config_for_test():
    from app.harness.agent_config import AgentConfig
    return AgentConfig(
        name="KnowledgeQA",
        display_name="知识库问答",
        es_index="qa_chunks",
        available_indexes=["qa_chunks", "ticket_knowledge", "sales_knowledge", "ops_knowledge"],
        max_steps=3,
        session_prefix="kqa_",
    )
