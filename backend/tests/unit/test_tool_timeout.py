"""Tests for tool timeout + retry mechanism (B1)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.harness.agent_loop import _execute_tool_with_retry
from app.harness.models import ToolHandler, ToolResult
from pydantic import BaseModel


class _DummyInput(BaseModel):
    query: str


def _make_handler(name="test_tool", timeout=1.0, max_retries=0, retryable_exceptions=(), fn=None):
    """Build a ToolHandler with given timeout/retry config."""
    return ToolHandler(
        name=name,
        input_schema=_DummyInput,
        fn=fn or AsyncMock(return_value=ToolResult(status="ok", summary="done")),
        timeout=timeout,
        max_retries=max_retries,
        retryable_exceptions=retryable_exceptions,
    )


class TestExecuteToolWithRetry:
    async def test_success_no_retry(self):
        """Normal success should not trigger any retry."""
        handler = _make_handler(timeout=5.0, max_retries=3)
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "ok"
        assert result.summary == "done"
        handler.fn.assert_awaited_once()

    async def test_timeout_triggers_retry(self):
        """First call times out, retry succeeds."""
        handler = _make_handler(timeout=0.05, max_retries=2)
        handler.fn = AsyncMock(side_effect=[
            asyncio.TimeoutError(),
            ToolResult(status="ok", summary="retry success"),
        ])
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "ok"
        assert result.summary == "retry success"
        assert handler.fn.await_count == 2

    async def test_timeout_exhausted_returns_error(self):
        """All retries exhausted due to timeout → error ToolResult."""
        handler = _make_handler(timeout=0.01, max_retries=2)
        handler.fn = AsyncMock(side_effect=asyncio.TimeoutError)
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "error"
        assert "重试耗尽" in result.summary
        assert result.data == {"retries_exhausted": True}
        assert handler.fn.await_count == 3  # 1 initial + 2 retries

    async def test_non_retryable_exception_no_retry(self):
        """Non-retryable exception returns error immediately, no retry."""
        handler = _make_handler(timeout=5.0, max_retries=3, retryable_exceptions=())
        handler.fn = AsyncMock(side_effect=ValueError("bad input"))
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "error"
        assert "bad input" in result.summary
        assert handler.fn.await_count == 1  # no retry

    async def test_retryable_exception_triggers_retry(self):
        """Retryable exception triggers retry, succeeds on second attempt."""
        handler = _make_handler(
            timeout=5.0, max_retries=2,
            retryable_exceptions=(ValueError, ConnectionError),
        )
        handler.fn = AsyncMock(side_effect=[
            ValueError("transient error"),
            ToolResult(status="ok", summary="recovered"),
        ])
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "ok"
        assert result.summary == "recovered"
        assert handler.fn.await_count == 2

    async def test_retryable_exception_exhausted_returns_error(self):
        """All retries exhausted on retryable exception → error."""
        handler = _make_handler(
            timeout=5.0, max_retries=1,
            retryable_exceptions=(ValueError,),
        )
        handler.fn = AsyncMock(side_effect=ValueError("persistent error"))
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "error"
        assert "重试耗尽" in result.summary
        assert handler.fn.await_count == 2

    async def test_max_retries_zero_no_retry_on_timeout(self):
        """max_retries=0 means no retry on timeout."""
        handler = _make_handler(timeout=0.01, max_retries=0)
        handler.fn = AsyncMock(side_effect=asyncio.TimeoutError)
        result = await _execute_tool_with_retry(handler, {"query": "test"})
        assert result.status == "error"
        assert handler.fn.await_count == 1


class TestDecoratorPassesTimeoutConfig:
    def test_decorator_passes_timeout_to_handler(self):
        """Verifies decorator parameters are forwarded to ToolHandler."""
        from app.harness.tool_registry import SHARED_TOOLS, register_shared
        from pydantic import BaseModel

        class TestInput(BaseModel):
            x: int

        old_shared = dict(SHARED_TOOLS)
        try:
            @register_shared("__test_timeout_tool", TestInput, timeout=7.5, max_retries=3)
            async def __test_timeout_tool(x: int):
                return ToolResult(status="ok", summary="ok")

            handler = SHARED_TOOLS["__test_timeout_tool"]
            assert handler.timeout == 7.5
            assert handler.max_retries == 3
            assert handler.retryable_exceptions == ()
        finally:
            SHARED_TOOLS.clear()
            SHARED_TOOLS.update(old_shared)

    def test_legacy_decorator_no_timeout_args(self):
        """Legacy register() without timeout args uses defaults."""
        from app.harness.tool_registry import TOOL_HANDLERS, register
        from pydantic import BaseModel

        class TestInput(BaseModel):
            y: str

        old_handlers = dict(TOOL_HANDLERS)
        try:
            @register("__test_legacy_timeout", TestInput)
            async def __test_legacy_timeout(y: str):
                return ToolResult(status="ok", summary="ok")

            handler = TOOL_HANDLERS["__test_legacy_timeout"]
            assert handler.timeout == 30.0  # default
            assert handler.max_retries == 0  # default
            assert handler.retryable_exceptions == ()  # default
        finally:
            TOOL_HANDLERS.clear()
            TOOL_HANDLERS.update(old_handlers)
