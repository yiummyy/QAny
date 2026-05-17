"""Unit tests for human-in-the-loop confirmation mechanism (Spec 2026-05-08)."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from app.harness.models import (
    ConfirmationRequest,
    ConfirmationResponse,
    ToolHandler,
    ToolResult,
)
from app.harness.agent_loop import (
    TOOL_LABEL_MAP,
    _build_confirmation_summary,
    _build_confirmation_request,
    _wait_for_confirmation,
    get_pending_confirmation,
    _pending_confirmations,
)
from app.harness.tool_registry import (
    register,
    register_agent_tool,
    register_shared,
    AGENT_TOOLS,
    SHARED_TOOLS,
    TOOL_HANDLERS,
)


# ---------------------------------------------------------------------------
# T1: ToolHandler new fields
# ---------------------------------------------------------------------------

class DummySchema(BaseModel):
    x: int = 1


async def test_toolhandler_defaults_no_confirmation():
    """ToolHandler defaults: requires_confirmation=False, confirmation_timeout=120.0."""
    h = ToolHandler(name="test", input_schema=DummySchema, fn=lambda: None)
    assert h.requires_confirmation is False
    assert h.confirmation_timeout == 120.0


async def test_toolhandler_with_confirmation():
    """ToolHandler accepts requires_confirmation=True and custom timeout."""
    h = ToolHandler(
        name="test", input_schema=DummySchema, fn=lambda: None,
        requires_confirmation=True, confirmation_timeout=60.0,
    )
    assert h.requires_confirmation is True
    assert h.confirmation_timeout == 60.0


async def test_toolhandler_serialization():
    """ToolHandler can be serialized via model_dump() including new fields."""
    h = ToolHandler(
        name="test", input_schema=DummySchema, fn=lambda: None,
        requires_confirmation=True, confirmation_timeout=90.0,
    )
    d = h.model_dump()
    assert d["requires_confirmation"] is True
    assert d["confirmation_timeout"] == 90.0


# ---------------------------------------------------------------------------
# ConfirmationRequest / ConfirmationResponse models
# ---------------------------------------------------------------------------


async def test_confirmation_request_valid():
    req = ConfirmationRequest(
        action_token="cfm_abc123",
        tool_name="create_ticket",
        tool_label="创建工单",
        summary="创建工单摘要",
        details={"title": "测试"},
        expires_at="2026-05-08T10:32:00Z",
    )
    assert req.action_token == "cfm_abc123"
    assert req.tool_name == "create_ticket"
    assert req.details == {"title": "测试"}


async def test_confirmation_request_default_details():
    """details field defaults to empty dict."""
    req = ConfirmationRequest(
        action_token="cfm_x",
        tool_name="escalate",
        tool_label="升级工单",
        summary="升级摘要",
        expires_at="2026-05-08T10:32:00Z",
    )
    assert req.details == {}


async def test_confirmation_response_valid():
    resp = ConfirmationResponse(action_token="cfm_abc", choice="approved")
    assert resp.choice == "approved"


async def test_confirmation_response_rejected():
    resp = ConfirmationResponse(action_token="cfm_abc", choice="rejected")
    assert resp.choice == "rejected"


async def test_confirmation_response_invalid_choice():
    """Arbitrary strings are accepted at the model level (validation at endpoint)."""
    resp = ConfirmationResponse(action_token="cfm_abc", choice="maybe")
    assert resp.choice == "maybe"


# ---------------------------------------------------------------------------
# _build_confirmation_summary
# ---------------------------------------------------------------------------


async def test_summary_create_ticket():
    summary = _build_confirmation_summary("create_ticket", {
        "title": "报销系统异常",
        "priority": "high",
        "category": "IT",
    })
    assert "报销系统异常" in summary
    assert "high" in summary
    assert "IT" in summary


async def test_summary_create_ticket_defaults():
    """Missing fields use fallback defaults."""
    summary = _build_confirmation_summary("create_ticket", {})
    assert "未知工单" in summary
    assert "medium" in summary
    assert "其他" in summary


async def test_summary_escalate():
    summary = _build_confirmation_summary("escalate", {
        "ticket_id": "tkt_abc123",
        "reason": "用户反馈紧急",
    })
    assert "tkt_abc123" in summary
    assert "urgent" in summary
    assert "用户反馈紧急" in summary


async def test_summary_escalate_defaults():
    summary = _build_confirmation_summary("escalate", {})
    assert "未知" in summary
    assert "未提供原因" in summary


async def test_summary_run_diagnostic():
    summary = _build_confirmation_summary("run_diagnostic", {
        "device_name": "逆变器-A01",
        "check_type": "connectivity",
    })
    assert "逆变器-A01" in summary
    assert "connectivity" in summary


async def test_summary_unknown_tool():
    summary = _build_confirmation_summary("unknown_action", {})
    assert "unknown_action" in summary


# ---------------------------------------------------------------------------
# TOOL_LABEL_MAP
# ---------------------------------------------------------------------------


async def test_label_map_coverage():
    assert TOOL_LABEL_MAP["create_ticket"] == "创建工单"
    assert TOOL_LABEL_MAP["escalate"] == "升级工单"
    assert TOOL_LABEL_MAP["run_diagnostic"] == "执行诊断"


# ---------------------------------------------------------------------------
# _pending_confirmations + get_pending_confirmation
# ---------------------------------------------------------------------------


async def test_pending_confirmations_register_and_lookup():
    event = asyncio.Event()
    token = "cfm_test123"
    _pending_confirmations[token] = event
    assert get_pending_confirmation(token) is event
    assert get_pending_confirmation("nonexistent") is None
    del _pending_confirmations[token]


# ---------------------------------------------------------------------------
# _wait_for_confirmation
# ---------------------------------------------------------------------------


async def test_wait_for_confirmation_approved():
    """Event is set with choice stored in Redis."""
    event = asyncio.Event()
    token = "cfm_wait_test"

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=json.dumps({
        "session_id": "s1", "status": "pending", "choice": "approved",
    }))
    mock_redis.delete = AsyncMock()

    with patch(
        "app.storage.redis_client.get_redis", return_value=mock_redis
    ):
        # Set event after a short delay to simulate user clicking confirm
        async def set_later():
            await asyncio.sleep(0.05)
            event.set()

        task = asyncio.create_task(set_later())
        result = await _wait_for_confirmation(token, event, timeout=2.0)
        await task

    assert result.action_token == token
    assert result.choice == "approved"


async def test_wait_for_confirmation_timeout():
    """Timeout returns rejected."""
    event = asyncio.Event()
    token = "cfm_timeout_test"

    mock_redis = MagicMock()
    mock_redis.delete = AsyncMock()

    with patch(
        "app.storage.redis_client.get_redis", return_value=mock_redis
    ):
        result = await _wait_for_confirmation(token, event, timeout=0.1)

    assert result.choice == "rejected"


async def test_wait_for_confirmation_cleans_up():
    """After (timeout or result), pending entry is removed and Redis key deleted."""
    event = asyncio.Event()
    token = f"cfm_cleanup_{time.time()}"

    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.delete = AsyncMock()

    _pending_confirmations[token] = event
    with patch(
        "app.storage.redis_client.get_redis", return_value=mock_redis
    ):
        result = await _wait_for_confirmation(token, event, timeout=0.1)

    assert token not in _pending_confirmations
    mock_redis.delete.assert_called()


# ---------------------------------------------------------------------------
# Tool registry passes through confirmation params
# ---------------------------------------------------------------------------


async def test_register_passes_confirmation_params():
    @register("cfm_reg_test", DummySchema,
              requires_confirmation=True, confirmation_timeout=30.0)
    async def cfm_tool(x: int = 1) -> ToolResult:
        return ToolResult(status="ok", summary="done")

    handler = TOOL_HANDLERS["cfm_reg_test"]
    assert handler.requires_confirmation is True
    assert handler.confirmation_timeout == 30.0
    # Clean up
    TOOL_HANDLERS.pop("cfm_reg_test", None)


async def test_register_shared_passes_confirmation_params():
    @register_shared("cfm_shared_test", DummySchema,
                     requires_confirmation=True, confirmation_timeout=45.0)
    async def cfm_shared(x: int = 1) -> ToolResult:
        return ToolResult(status="ok", summary="done")

    handler = SHARED_TOOLS["cfm_shared_test"]
    assert handler.requires_confirmation is True
    assert handler.confirmation_timeout == 45.0
    SHARED_TOOLS.pop("cfm_shared_test", None)
    TOOL_HANDLERS.pop("cfm_shared_test", None)


async def test_register_agent_tool_passes_confirmation_params():
    @register_agent_tool("TestAgent", "cfm_agent_test", DummySchema,
                         requires_confirmation=True, confirmation_timeout=60.0)
    async def cfm_agent(x: int = 1) -> ToolResult:
        return ToolResult(status="ok", summary="done")

    handler = AGENT_TOOLS["TestAgent"]["cfm_agent_test"]
    assert handler.requires_confirmation is True
    assert handler.confirmation_timeout == 60.0
    AGENT_TOOLS.pop("TestAgent", None)
