"""Task 6: Provider contract tests using respx to mock HTTP."""

import json

import pytest
import respx

from app.providers.dashscope_provider import DASHSCOPE_BASE, DashScopeProvider
from app.providers.deepseek_provider import DEEPSEEK_BASE, DeepSeekProvider
from app.providers.router import ProviderRouter


@pytest.fixture
def dashscope_provider():
    with respx.mock:
        yield DashScopeProvider(model="qwen-turbo")


@pytest.fixture
def deepseek_provider():
    with respx.mock:
        yield DeepSeekProvider(model="deepseek-chat")


async def test_dashscope_chat_returns_content(dashscope_provider):
    respx.post(f"{DASHSCOPE_BASE}/chat/completions").respond(
        json={
            "choices": [{"message": {"content": "你好，有什么可以帮助你的？"}}],
            "usage": {"total_tokens": 15},
        }
    )
    result = await dashscope_provider.chat([{"role": "user", "content": "你好"}])
    assert "你好" in result


async def test_dashscope_chat_api_error(dashscope_provider):
    respx.post(f"{DASHSCOPE_BASE}/chat/completions").respond(401, json={"error": "unauthorized"})
    with pytest.raises(RuntimeError, match="DashScope API error"):
        await dashscope_provider.chat([{"role": "user", "content": "hi"}])


async def test_dashscope_stream_chat(dashscope_provider):
    sse_data = (
        'data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"世界"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(f"{DASHSCOPE_BASE}/chat/completions").respond(200, content=sse_data.encode())
    chunks = [c async for c in dashscope_provider.stream_chat([{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "你好世界"


async def test_dashscope_stream_api_error(dashscope_provider):
    respx.post(f"{DASHSCOPE_BASE}/chat/completions").respond(500, json={"error": "internal"})
    with pytest.raises(RuntimeError, match="DashScope API error"):
        async for _ in dashscope_provider.stream_chat([{"role": "user", "content": "hi"}]):
            pass


async def test_deepseek_chat_returns_content(deepseek_provider):
    respx.post(f"{DEEPSEEK_BASE}/chat/completions").respond(
        json={
            "choices": [{"message": {"content": "DeepSeek response"}}],
            "usage": {"total_tokens": 10},
        }
    )
    result = await deepseek_provider.chat([{"role": "user", "content": "test"}])
    assert "DeepSeek" in result


async def test_deepseek_chat_api_error(deepseek_provider):
    respx.post(f"{DEEPSEEK_BASE}/chat/completions").respond(503, json={"error": "unavailable"})
    with pytest.raises(RuntimeError, match="DeepSeek API error"):
        await deepseek_provider.chat([{"role": "user", "content": "hi"}])


async def test_deepseek_stream_chat(deepseek_provider):
    sse_data = (
        'data: {"choices":[{"delta":{"content":"流式"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"输出"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(f"{DEEPSEEK_BASE}/chat/completions").respond(200, content=sse_data.encode())
    chunks = [c async for c in deepseek_provider.stream_chat([{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "流式输出"


async def test_dashscope_plan_returns_decision(dashscope_provider):
    respx.post(f"{DASHSCOPE_BASE}/chat/completions").respond(
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"type": "tool_call", "tool": "hybrid_search", "args": {"query": "年假"}}
                        )
                    }
                }
            ]
        }
    )
    result = await dashscope_provider.plan(
        [{"role": "user", "content": "年假怎么申请？"}],
        [{"name": "hybrid_search", "description": "搜索知识库"}],
    )
    assert result["type"] == "tool_call"
    assert result["tool"] == "hybrid_search"


async def test_deepseek_plan_returns_decision(deepseek_provider):
    respx.post(f"{DEEPSEEK_BASE}/chat/completions").respond(
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"type": "tool_call", "tool": "hybrid_search", "args": {"query": "test"}}
                        )
                    }
                }
            ]
        }
    )
    result = await deepseek_provider.plan(
        [{"role": "user", "content": "test"}],
        [{"name": "hybrid_search", "description": "search"}],
    )
    assert result["type"] == "tool_call"


async def test_provider_router_contract():
    """Router switches from failing primary to working fallback."""
    with respx.mock:
        # Primary: always timeout
        respx.post(f"{DASHSCOPE_BASE}/chat/completions").respond(500)
        # Fallback: works
        respx.post(f"{DEEPSEEK_BASE}/chat/completions").respond(
            json={"choices": [{"message": {"content": "fallback worked"}}]}
        )

        primary = DashScopeProvider(model="qwen-turbo")
        fallback = DeepSeekProvider(model="deepseek-chat")
        router = ProviderRouter(primary=primary, fallback=fallback, timeout=2.0)

        result = await router.chat([{"role": "user", "content": "hi"}])
        assert "fallback" in result
