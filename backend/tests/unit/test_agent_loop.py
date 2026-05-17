"""Task 9: Agent loop tests — updated for AgentConfig refactoring."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.agent_config import AgentConfig
from app.harness.agent_loop import _default_plan, run
from app.harness.models import Context, Event, EventType


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


@pytest.fixture
def agent_config():
    return AgentConfig(
        name="KnowledgeQA",
        display_name="知识库问答",
        es_index="qa_chunks",
        max_steps=3,
        session_prefix="kqa_",
    )


def _make_mock_tool(status="ok", summary="success", data=None):
    async def mock_tool(**kwargs):
        from app.harness.models import ToolResult
        return ToolResult(status=status, summary=summary, data=data or {})
    return mock_tool


@pytest.fixture
def mock_deps():
    """Mock all dependencies for agent loop including tool handlers."""
    mock_tools = {
        "search_knowledge": _make_mock_tool(
            "ok", "检索完成: 路由至qa_chunks → 召回5条 → 重排5条(最高分0.90)",
            {"chunks": [{"_id": "c1", "content": "test", "rerank_score": 0.9, "doc_name": "doc1"}],
             "intent": "制度查询", "rewritten_query": "年假怎么申请",
             "diagnostics": {"raw_hit_count": 12, "rerank_top_score": 0.90, "permission_filtered": 0}},
        ),
        "generate_answer": _make_mock_tool(
            "ok", "基于5个片段生成答案",
            {"prompt": "prompt", "chunks": [{"_id": "c1", "content": "test", "rerank_score": 0.9, "doc_name": "doc1"}]},
        ),
        "query_knowledge": _make_mock_tool(
            "ok", "基于5个片段生成答案",
            {"prompt": "prompt", "chunks": [{"_id": "c1", "content": "test", "rerank_score": 0.9, "doc_name": "doc1"}]},
        ),
        "hallucination_check": _make_mock_tool(
            "ok", "no hallucination", {"score": 0.92, "verdict": "high"},
        ),
    }

    with (
        patch("app.harness.agent_loop.build", new_callable=AsyncMock) as mock_build,
        patch("app.harness.agent_loop.append", new_callable=AsyncMock) as mock_append,
        patch("app.harness.agent_loop.save_task", new_callable=AsyncMock) as mock_save_task,
        patch("app.harness.agent_loop.compact", new_callable=AsyncMock) as mock_compact,
    ):
        ctx = Context(
            system_prompt="test system prompt for admin L3",
            messages=[{"role": "user", "content": "年假怎么申请？"}],
        )
        mock_build.return_value = ctx
        mock_compact.side_effect = lambda c: c  # no-op

        yield {
            "build": mock_build,
            "append": mock_append,
            "save_task": mock_save_task,
            "compact": mock_compact,
            "ctx": ctx,
            "mock_tools": mock_tools,
        }


@pytest.fixture
def agent_config_for_test():
    return AgentConfig(
        name="KnowledgeQA",
        display_name="知识库问答",
        es_index="qa_chunks",
        max_steps=3,
        session_prefix="kqa_",
    )


async def test_run_yields_status_then_done(admin_claims, mock_deps, agent_config_for_test):
    """Without a provider, uses default plan: search_knowledge → final_answer."""
    # Register mock handlers
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        events = []
        async for ev in run("年假怎么申请？", "sess-1", admin_claims,
                            agent_config=agent_config_for_test, provider_router=None):
            events.append(ev)

        event_types = [e.type for e in events]
        assert EventType.STATUS in event_types
        assert EventType.DONE in event_types
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_run_completes_within_max_steps(admin_claims, mock_deps, agent_config_for_test):
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        events = []
        async for ev in run("查询", "sess-b", admin_claims,
                            agent_config=agent_config_for_test, provider_router=None):
            events.append(ev)

        done_events = [e for e in events if e.type == EventType.DONE]
        error_events = [e for e in events if e.type == EventType.ERROR]
        assert len(done_events) >= 1
        assert len(error_events) == 0
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_run_writes_user_message_to_session(admin_claims, mock_deps, agent_config_for_test):
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        async for _ in run("测试问题", "sess-a", admin_claims,
                           agent_config=agent_config_for_test, provider_router=None):
            pass

        user_calls = [c for c in mock_deps["append"].call_args_list
                      if c[0][1].get("type") == "user"]
        assert len(user_calls) >= 1
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_run_returns_events(admin_claims, mock_deps, agent_config_for_test):
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        events = [e async for e in run("查询", "sess-c", admin_claims,
                                        agent_config=agent_config_for_test, provider_router=None)]
        assert len(events) > 0
        for ev in events:
            assert isinstance(ev, Event)
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_run_yields_status_phases_in_order(admin_claims, mock_deps, agent_config_for_test):
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        events = [e async for e in run("查询", "sess-f", admin_claims,
                                        agent_config=agent_config_for_test, provider_router=None)]
        status_events = [(e.type, e.data.get("phase")) for e in events if e.type == EventType.STATUS]
        assert status_events[0][1] == "planning"
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_default_plan_step_0_is_search_knowledge():
    agent_config = AgentConfig(name="KnowledgeQA")
    ctx = Context(system_prompt="sp")
    decision = _default_plan(ctx, 0, agent_config)
    assert decision.type == "tool_call"
    assert decision.tool == "search_knowledge"


async def test_default_plan_step_1_is_final_answer():
    agent_config = AgentConfig(name="KnowledgeQA")
    ctx = Context(system_prompt="sp")
    decision = _default_plan(ctx, 1, agent_config)
    assert decision.type == "final_answer"


async def test_default_plan_beyond_first_step_is_final():
    agent_config = AgentConfig(name="KnowledgeQA")
    ctx = Context(system_prompt="sp")
    decision = _default_plan(ctx, 10, agent_config)
    assert decision.type == "final_answer"


async def test_run_with_provider_router_uses_plan(admin_claims, mock_deps, agent_config_for_test):
    """When a provider router is given, it attempts to use it for plan decisions."""
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        mock_router = MagicMock()
        mock_router.plan = AsyncMock(return_value={"type": "final_answer"})

        events = []
        async for ev in run("查询", "sess-d", admin_claims,
                            agent_config=agent_config_for_test, provider_router=mock_router):
            events.append(ev)

        mock_router.plan.assert_called()
        assert any(e.type == EventType.DONE for e in events)
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_run_handles_provider_plan_failure(admin_claims, mock_deps, agent_config_for_test):
    """When provider fails, falls back to default plan pipeline."""
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        mock_router = MagicMock()
        mock_router.plan = AsyncMock(side_effect=RuntimeError("timeout"))

        events = []
        async for ev in run("查询", "sess-e", admin_claims,
                            agent_config=agent_config_for_test, provider_router=mock_router):
            events.append(ev)

        assert any(e.type == EventType.DONE for e in events)
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)


async def test_session_id_is_prefixed(admin_claims, mock_deps, agent_config_for_test):
    """Session ID passed to build should include the agent prefix."""
    from app.harness.tool_registry import SHARED_TOOLS
    from app.harness.models import ToolHandler
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        pass

    old_shared = dict(SHARED_TOOLS)
    try:
        for name, fn in mock_deps["mock_tools"].items():
            SHARED_TOOLS[name] = ToolHandler(name=name, input_schema=DummyInput, fn=fn)

        async for _ in run("查询", "sess-xyz", admin_claims,
                           agent_config=agent_config_for_test, provider_router=None):
            pass

        build_args = mock_deps["build"].call_args
        assert build_args[0][0] == "kqa_sess-xyz"
    finally:
        SHARED_TOOLS.clear()
        SHARED_TOOLS.update(old_shared)
