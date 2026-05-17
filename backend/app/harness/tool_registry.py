"""Tool registry — two-tier: SHARED_TOOLS + AGENT_TOOLS with override support."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from app.harness.models import ToolHandler

# ---- Legacy global registry (backward compat) ----
TOOL_HANDLERS: dict[str, ToolHandler] = {}

# ---- Shared tools (available to ALL agents) ----
SHARED_TOOLS: dict[str, ToolHandler] = {}

# ---- Agent-specific tool registrations ----
AGENT_TOOLS: dict[str, dict[str, ToolHandler]] = {}


def register(
    name: str,
    schema: type[BaseModel],
    timeout: float = 30.0,
    max_retries: int = 0,
    retryable_exceptions: Any = (),
    requires_confirmation: bool = False,
    confirmation_timeout: float = 120.0,
) -> Callable:
    """Decorator that registers an async tool function into TOOL_HANDLERS.

    Kept for backward compatibility. New tools should use register_shared()
    or register_agent_tool().
    """

    def deco(fn: Any) -> Any:
        TOOL_HANDLERS[name] = ToolHandler(
            name=name, input_schema=schema, fn=fn,
            timeout=timeout, max_retries=max_retries,
            retryable_exceptions=retryable_exceptions,
            requires_confirmation=requires_confirmation,
            confirmation_timeout=confirmation_timeout,
        )
        return fn

    return deco


def register_shared(
    name: str,
    schema: type[BaseModel],
    timeout: float = 30.0,
    max_retries: int = 0,
    retryable_exceptions: Any = (),
    requires_confirmation: bool = False,
    confirmation_timeout: float = 120.0,
) -> Callable:
    """Register a tool available to ALL agents."""

    def deco(fn: Any) -> Any:
        handler = ToolHandler(
            name=name, input_schema=schema, fn=fn,
            timeout=timeout, max_retries=max_retries,
            retryable_exceptions=retryable_exceptions,
            requires_confirmation=requires_confirmation,
            confirmation_timeout=confirmation_timeout,
        )
        SHARED_TOOLS[name] = handler
        # Also register in legacy TOOL_HANDLERS for backward compat
        TOOL_HANDLERS[name] = handler
        return fn

    return deco


def register_agent_tool(
    agent_name: str,
    name: str,
    schema: type[BaseModel],
    timeout: float = 30.0,
    max_retries: int = 0,
    retryable_exceptions: Any = (),
    requires_confirmation: bool = False,
    confirmation_timeout: float = 120.0,
) -> Callable:
    """Register a tool available ONLY to a specific agent."""

    def deco(fn: Any) -> Any:
        AGENT_TOOLS.setdefault(agent_name, {})[name] = ToolHandler(
            name=name, input_schema=schema, fn=fn,
            timeout=timeout, max_retries=max_retries,
            retryable_exceptions=retryable_exceptions,
            requires_confirmation=requires_confirmation,
            confirmation_timeout=confirmation_timeout,
        )
        return fn

    return deco


def build_agent_handlers(agent_config: Any) -> dict[str, ToolHandler]:
    """Build the final tool map for an agent: shared + agent-specific.

    Agent-specific tools override shared tools of the same name.
    extra_tools on the AgentConfig also override both.
    """
    handlers = dict(SHARED_TOOLS)
    agent_specific = AGENT_TOOLS.get(agent_config.name, {})
    handlers.update(agent_specific)
    handlers.update(agent_config.extra_tools)
    return handlers
