"""Task 1: Harness Models contract tests."""

import pytest

from app.harness.models import Context, Event, EventType, PlanDecision, ToolHandler, ToolResult


def test_tool_result_creation():
    tr = ToolResult(status="ok", summary="检索完成，召回 18 条", data={"chunks": []})
    assert tr.status == "ok"
    assert "检索完成" in tr.summary
    assert tr.data == {"chunks": []}


def test_tool_result_failed():
    tr = ToolResult(status="error", summary="ES 不可达", data=None)
    assert tr.status == "error"
    assert tr.data is None


def test_tool_result_degraded():
    tr = ToolResult(status="degraded", summary="降级为模板回答", data={"fallback": True})
    assert tr.status == "degraded"


def test_event_message():
    ev = Event(type=EventType.MESSAGE, data={"chunk": "你好"})
    assert ev.type == EventType.MESSAGE
    assert ev.data["chunk"] == "你好"


def test_event_done():
    ev = Event(type=EventType.DONE, data={"sources": [], "confidence": "high"})
    assert ev.type == EventType.DONE
    assert ev.data["confidence"] == "high"


def test_event_status():
    ev = Event(type=EventType.STATUS, data={"phase": "retrieving", "message": "正在检索..."})
    assert ev.type == EventType.STATUS
    assert ev.data["phase"] == "retrieving"


def test_event_error():
    ev = Event(type=EventType.ERROR, data={"code": 50000, "message": "timeout"})
    assert ev.type == EventType.ERROR


def test_plan_decision_tool_call():
    pd = PlanDecision(type="tool_call", tool="hybrid_search", args={"query": "test"})
    assert pd.type == "tool_call"
    assert pd.tool == "hybrid_search"
    assert pd.args == {"query": "test"}


def test_plan_decision_final_answer():
    pd = PlanDecision(type="final_answer")
    assert pd.type == "final_answer"
    assert pd.tool is None


def test_plan_decision_with_metadata():
    pd = PlanDecision(type="tool_call", tool="rerank", args={"top_k": 5}, metadata={"reason": "精排"})
    assert pd.metadata == {"reason": "精排"}


def test_context_token_count():
    ctx = Context(
        system_prompt="You are helpful.",
        messages=[{"role": "user", "content": "什么是年假？"}],
        tool_results=[],
    )
    assert ctx.token_count() > 0


def test_context_token_count_increases_with_messages():
    ctx = Context(system_prompt="sys", messages=[], tool_results=[])
    before = ctx.token_count()
    ctx.messages.append({"role": "user", "content": "一个很长的问题" * 20})
    assert ctx.token_count() > before


def test_context_append_tool_result():
    ctx = Context(system_prompt="", messages=[], tool_results=[])
    ctx.append_tool_result("hybrid_search", ToolResult(status="ok", summary="ok"))
    assert len(ctx.tool_results) == 1
    assert ctx.tool_results[0]["tool"] == "hybrid_search"
    assert ctx.tool_results[0]["status"] == "ok"


def test_context_append_multiple_tool_results():
    ctx = Context(system_prompt="", messages=[], tool_results=[])
    ctx.append_tool_result("t1", ToolResult(status="ok", summary="s1"))
    ctx.append_tool_result("t2", ToolResult(status="ok", summary="s2"))
    assert len(ctx.tool_results) == 2


def test_tool_handler_creation():
    from pydantic import BaseModel

    class DummyInput(BaseModel):
        x: int

    async def dummy_fn(**kwargs):
        pass

    th = ToolHandler(name="dummy", input_schema=DummyInput, fn=dummy_fn)
    assert th.name == "dummy"
    assert th.input_schema is DummyInput


def test_context_compacted_summary_default_none():
    ctx = Context(system_prompt="sys")
    assert ctx._compacted_summary is None


def test_event_default_data():
    ev = Event(type=EventType.DONE)
    assert ev.data == {}
