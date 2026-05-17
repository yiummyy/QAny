"""Task 6: Provider unit tests (mocked HTTP)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.base import BaseLLMProvider, ChatMessage
from app.providers.dashscope_provider import DashScopeProvider, _parse_plan_response
from app.providers.deepseek_provider import DeepSeekProvider
from app.providers.router import ProviderRouter


class MockProvider(BaseLLMProvider):
    """Mock provider for testing router logic."""

    def __init__(self, name="mock", should_fail=False):
        self.name = name
        self.should_fail = should_fail
        self.chat_calls = 0
        self.stream_calls = 0
        self.plan_calls = 0

    async def chat(self, messages, **kwargs):
        self.chat_calls += 1
        if self.should_fail:
            raise RuntimeError("mock failure")
        return f"reply from {self.name}"

    async def stream_chat(self, messages, **kwargs):
        self.stream_calls += 1
        if self.should_fail:
            raise RuntimeError("mock stream failure")
        yield f"chunk1 from {self.name}"
        yield f"chunk2 from {self.name}"

    async def plan(self, messages, tools_schema):
        self.plan_calls += 1
        if self.should_fail:
            raise TimeoutError("mock timeout")
        return {"type": "tool_call", "tool": "hybrid_search", "args": {"query": "test"}}


async def test_router_primary_chat_succeeds():
    primary = MockProvider("primary")
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary=primary, fallback=fallback)

    result = await router.chat([{"role": "user", "content": "hello"}])
    assert "primary" in result
    assert primary.chat_calls == 1
    assert fallback.chat_calls == 0


async def test_router_fallback_on_primary_chat_failure():
    primary = MockProvider("primary", should_fail=True)
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary=primary, fallback=fallback, timeout=0.5)

    result = await router.chat([{"role": "user", "content": "hello"}])
    assert "fallback" in result
    assert fallback.chat_calls == 1


async def test_router_raises_when_both_fail():
    primary = MockProvider("primary", should_fail=True)
    fallback = MockProvider("fallback", should_fail=True)
    router = ProviderRouter(primary=primary, fallback=fallback, timeout=0.5)

    with pytest.raises(RuntimeError):
        await router.chat([{"role": "user", "content": "hello"}])


async def test_router_raises_when_primary_fails_no_fallback():
    primary = MockProvider("primary", should_fail=True)
    router = ProviderRouter(primary=primary, fallback=None, timeout=0.5)

    with pytest.raises(RuntimeError):
        await router.chat([{"role": "user", "content": "hello"}])


async def test_router_stream_fallback():
    primary = MockProvider("primary", should_fail=True)
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary=primary, fallback=fallback, timeout=0.5)

    chunks = [c async for c in router.stream_chat([{"role": "user", "content": "hi"}])]
    assert any("fallback" in c for c in chunks)


async def test_router_plan_fallback():
    primary = MockProvider("primary", should_fail=True)
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary=primary, fallback=fallback, timeout=0.5)

    result = await router.plan([{"role": "user", "content": "hi"}], [])
    assert result["type"] == "tool_call"


async def test_router_plan_primary_succeeds():
    primary = MockProvider("primary")
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary=primary, fallback=fallback)

    result = await router.plan([], [])
    assert result["tool"] == "hybrid_search"
    assert fallback.plan_calls == 0


def test_parse_plan_response_direct_json():
    result = _parse_plan_response('{"type": "tool_call", "tool": "search", "args": {"q": "test"}}')
    assert result["type"] == "tool_call"
    assert result["tool"] == "search"


def test_parse_plan_response_with_markdown_fence():
    response = '```json\n{"type": "final_answer"}\n```'
    result = _parse_plan_response(response)
    assert result["type"] == "final_answer"


def test_parse_plan_response_with_fence_no_lang():
    response = '```\n{"type": "tool_call", "tool": "rerank"}\n```'
    result = _parse_plan_response(response)
    assert result["type"] == "tool_call"


def test_base_provider_is_abstract():
    """Cannot instantiate abstract provider."""
    with pytest.raises(TypeError):
        BaseLLMProvider()


async def test_router_stream_primary_succeeds():
    primary = MockProvider("primary")
    fallback = MockProvider("fallback")
    router = ProviderRouter(primary=primary, fallback=fallback)

    chunks = [c async for c in router.stream_chat([])]
    assert all("primary" in c for c in chunks)
    assert fallback.stream_calls == 0
