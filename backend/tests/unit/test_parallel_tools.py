"""Tests for parallel tool invocation (B11)."""

import asyncio

import pytest

from app.harness.agent_loop import _execute_tools
from app.harness.models import Context, PlanDecision, ToolCall, ToolHandler, ToolResult
from pydantic import BaseModel


class _DummyInput(BaseModel):
    query: str = ""


def _make_handler(name="test_tool", delay=0.0, result=None):
    """Build a ToolHandler with a configurable delay."""
    async def _fn(**kwargs):
        if delay:
            await asyncio.sleep(delay)
        if result is not None:
            return result
        return ToolResult(status="ok", summary=f"{name} done")

    return ToolHandler(name=name, input_schema=_DummyInput, fn=_fn, timeout=5.0)


def _make_ctx():
    """Build a minimal Context for tool execution."""
    return Context(system_prompt="test")


class TestExecuteTools:
    async def test_single_tool_via_legacy_tool_field(self):
        """Legacy decision.tool still works."""
        handler = _make_handler("search_knowledge")
        decision = PlanDecision(type="tool_call", tool="search_knowledge", args={"query": "test"})
        handlers = {"search_knowledge": handler}

        results = await _execute_tools(decision, handlers, None, None, None, _make_ctx())
        assert len(results) == 1
        assert results[0][0] == "search_knowledge"
        assert results[0][1].status == "ok"

    async def test_parallel_two_tools(self):
        """Two independent tools execute in parallel."""
        h1 = _make_handler("search_knowledge", delay=0.05)
        h2 = _make_handler("lookup_ticket", delay=0.05)
        decision = PlanDecision(type="tool_call", tools=[
            ToolCall(tool="search_knowledge", args={"query": "q1"}),
            ToolCall(tool="lookup_ticket", args={"ticket_id": "t1"}),
        ])
        handlers = {"search_knowledge": h1, "lookup_ticket": h2}

        start = asyncio.get_event_loop().time()
        results = await _execute_tools(decision, handlers, None, None, None, _make_ctx())
        elapsed = asyncio.get_event_loop().time() - start

        assert len(results) == 2
        # Parallel execution: total time < sum of individual delays (0.05 + 0.05 = 0.1)
        assert elapsed < 0.09  # should be ~0.05s

    async def test_parallel_preserves_order(self):
        """Results are returned in the original tool_calls order."""
        h1 = _make_handler("tool_a", delay=0.03)
        h2 = _make_handler("tool_b", delay=0.01)  # faster
        decision = PlanDecision(type="tool_call", tools=[
            ToolCall(tool="tool_a"),
            ToolCall(tool="tool_b"),
        ])
        handlers = {"tool_a": h1, "tool_b": h2}

        results = await _execute_tools(decision, handlers, None, None, None, _make_ctx())
        # Order preserved despite tool_b being faster
        assert results[0][0] == "tool_a"
        assert results[1][0] == "tool_b"

    async def test_unknown_tool_returns_error(self):
        """Unknown tool in parallel list returns error for that tool only."""
        h1 = _make_handler("known_tool")
        decision = PlanDecision(type="tool_call", tools=[
            ToolCall(tool="known_tool"),
            ToolCall(tool="nonexistent"),
        ])
        handlers = {"known_tool": h1}

        results = await _execute_tools(decision, handlers, None, None, None, _make_ctx())
        assert len(results) == 2
        assert results[0][1].status == "ok"
        assert results[1][1].status == "error"
        assert "未知工具" in results[1][1].summary

    async def test_one_tool_fails_others_continue(self):
        """When one tool fails, other parallel tools still complete."""
        h1 = _make_handler("tool_ok")
        h2 = _make_handler("tool_fail")
        h2.fn = _make_handler("tool_fail", result=ToolResult(status="error", summary="fail")).fn
        decision = PlanDecision(type="tool_call", tools=[
            ToolCall(tool="tool_ok"),
            ToolCall(tool="tool_fail"),
        ])
        handlers = {"tool_ok": h1, "tool_fail": h2}

        results = await _execute_tools(decision, handlers, None, None, None, _make_ctx())
        assert results[0][1].status == "ok"
        assert results[1][1].status == "error"

    async def test_empty_tools_returns_empty(self):
        """Empty tools list returns empty results."""
        decision = PlanDecision(type="tool_call")
        results = await _execute_tools(decision, {}, None, None, None, None)
        assert results == []

    async def test_three_parallel_tools(self):
        """Three tools in parallel all complete."""
        handlers = {
            "a": _make_handler("a", delay=0.02),
            "b": _make_handler("b", delay=0.02),
            "c": _make_handler("c", delay=0.02),
        }
        decision = PlanDecision(type="tool_call", tools=[
            ToolCall(tool="a"), ToolCall(tool="b"), ToolCall(tool="c"),
        ])

        start = asyncio.get_event_loop().time()
        results = await _execute_tools(decision, handlers, None, None, None, _make_ctx())
        elapsed = asyncio.get_event_loop().time() - start

        assert len(results) == 3
        assert all(r[1].status == "ok" for r in results)
        assert elapsed < 0.08  # parallel ~0.02s, not 0.06s


class TestPlanDecisionModel:
    def test_plan_decision_single_tool_backward_compat(self):
        """Legacy single-tool PlanDecision still works."""
        d = PlanDecision(type="tool_call", tool="search_knowledge", args={"query": "x"})
        assert d.tool == "search_knowledge"
        assert d.tools is None
        assert d.reasoning is None

    def test_plan_decision_multi_tool(self):
        """New multi-tool PlanDecision."""
        d = PlanDecision(type="tool_call", tools=[
            ToolCall(tool="search_knowledge", args={"query": "a"}),
            ToolCall(tool="lookup_ticket", args={"ticket_id": "t1"}),
        ], reasoning="同时查知识库和工单")
        assert len(d.tools) == 2
        assert d.tool is None  # not using legacy field
        assert "工单" in d.reasoning

    def test_plan_decision_final_answer(self):
        """final_answer type has no tools."""
        d = PlanDecision(type="final_answer")
        assert d.tool is None
        assert d.tools is None

    def test_tool_call_default_args(self):
        """ToolCall args default to empty dict."""
        tc = ToolCall(tool="test")
        assert tc.args == {}
