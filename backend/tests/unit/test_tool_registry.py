"""Task 4: Tool Registry tests."""

import pytest
from pydantic import BaseModel

from app.harness.models import ToolHandler, ToolResult
from app.harness.tool_registry import TOOL_HANDLERS, register


class DummyInput(BaseModel):
    query: str
    top_k: int = 10


async def test_register_adds_to_handlers():
    @register("test_tool_1", DummyInput)
    async def test_tool_1(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary=f"searched {query}")

    assert "test_tool_1" in TOOL_HANDLERS
    handler = TOOL_HANDLERS["test_tool_1"]
    assert handler.name == "test_tool_1"
    assert handler.input_schema is DummyInput


async def test_register_preserves_function():
    @register("test_tool_2", DummyInput)
    async def test_tool_2(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary=query)

    handler = TOOL_HANDLERS["test_tool_2"]
    result = await handler.fn(query="hello")
    assert result.status == "ok"
    assert result.summary == "hello"


async def test_register_name_conflict_overwrites():
    @register("duplicate_tool", DummyInput)
    async def first_impl(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary="first")

    @register("duplicate_tool", DummyInput)
    async def second_impl(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary="second")

    handler = TOOL_HANDLERS["duplicate_tool"]
    result = await handler.fn(query="x")
    assert result.summary == "second"  # overwritten


async def test_register_multiple_tools():
    @register("tool_a", DummyInput)
    async def tool_a(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary="a")

    @register("tool_b", DummyInput)
    async def tool_b(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary="b")

    assert "tool_a" in TOOL_HANDLERS
    assert "tool_b" in TOOL_HANDLERS


async def test_register_returns_original_function():
    @register("return_test", DummyInput)
    async def return_test(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary=query)

    # The decorated function should still be callable directly
    result = await return_test(query="direct call")
    assert result.summary == "direct call"


async def test_tool_handler_type():
    @register("type_test", DummyInput)
    async def type_test(query: str, top_k: int = 10) -> ToolResult:
        return ToolResult(status="ok", summary="test")

    handler = TOOL_HANDLERS["type_test"]
    assert isinstance(handler, ToolHandler)
