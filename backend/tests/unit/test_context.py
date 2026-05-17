"""Task 3: Context assembly + compression tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.harness.context import COMPACT_THRESHOLD, build, compact
from app.harness.models import Context, ToolResult


@pytest.fixture
def mock_session_store():
    with patch("app.harness.context.get_history", new_callable=AsyncMock) as mock:
        mock.return_value = []
        yield mock


@pytest.fixture
def mock_llm():
    with patch("app.harness.context._compact_summarize", new_callable=AsyncMock) as mock:
        mock.return_value = "This is a compacted summary of the conversation."
        yield mock


@pytest.fixture
def mock_provider():
    """Mock provider_router for compact tests that need LLM summarization."""
    return MagicMock()


@pytest.fixture
def user_claims():
    from app.auth.claims import Role, UserClaims

    return UserClaims(
        sub="u1",
        username="admin",
        role=Role.ADMIN,
        pl="L3",
        dept=None,
        jti="jti-1",
    )


async def test_build_returns_context(mock_session_store, user_claims):
    ctx = await build("sess-1", "什么是年假？", user_claims)
    assert isinstance(ctx, Context)
    assert "年假" in ctx.messages[-1]["content"]


async def test_build_sets_system_prompt(mock_session_store, user_claims):
    ctx = await build("sess-2", "查询制度", user_claims)
    assert len(ctx.system_prompt) > 0
    assert ctx.system_prompt is not None


async def test_build_includes_user_query_as_message(mock_session_store, user_claims):
    ctx = await build("sess-3", "测试问题", user_claims)
    user_msgs = [m for m in ctx.messages if m["role"] == "user"]
    assert len(user_msgs) >= 1
    assert user_msgs[-1]["content"] == "测试问题"


async def test_build_loads_history(mock_session_store, user_claims):
    mock_session_store.return_value = [
        {"type": "user", "content": "之前的问题"},
        {"type": "assistant_done", "sources": []},
    ]
    ctx = await build("sess-4", "新问题", user_claims)
    # History should be loaded into messages
    assert len(ctx.messages) >= 2


async def test_build_includes_permission_info(mock_session_store, user_claims):
    ctx = await build("sess-5", "问题", user_claims)
    assert "L3" in ctx.system_prompt or "admin" in ctx.system_prompt.lower()


async def test_compact_below_threshold_skips(mock_llm, mock_provider):
    ctx = Context(
        system_prompt="短 prompt",
        messages=[{"role": "user", "content": "短问题"}],
    )
    result = await compact(ctx, mock_provider)
    mock_llm.assert_not_called()
    # Should return same object (or equivalent) when below threshold
    assert result is ctx


async def test_compact_above_threshold_triggers_llm(mock_llm, mock_provider):
    # Create a context with lots of content to exceed threshold
    long_content = "这是一个很长的对话内容。" * 500  # way over 3000 tokens
    ctx = Context(
        system_prompt="You are a helpful assistant." * 20,
        messages=[
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
        ],
        tool_results=[
            {"tool": "hybrid_search", "summary": long_content[:500], "status": "ok"},
        ],
    )
    assert ctx.token_count() > COMPACT_THRESHOLD
    result = await compact(ctx, mock_provider)
    mock_llm.assert_called_once()
    assert result._compacted_summary is not None


async def test_compact_preserves_compacted_summary(mock_llm, mock_provider):
    mock_llm.return_value = "摘要：用户询问了年假制度。"
    long_content = "这是一个很长的对话内容用来测试压缩功能。" * 300
    extra_content = "额外填充内容以确保超过阈值。" * 100
    ctx = Context(
        system_prompt="You are a helpful assistant for enterprise knowledge management." * 30,
        messages=[
            {"role": "user", "content": long_content + extra_content},
            {"role": "assistant", "content": long_content},
        ],
    )
    assert ctx.token_count() > COMPACT_THRESHOLD
    result = await compact(ctx, mock_provider)
    mock_llm.assert_called_once()
    assert result._compacted_summary == "摘要：用户询问了年假制度。"


async def test_compact_clears_old_tool_results(mock_llm, mock_provider):
    mock_llm.return_value = "摘要"
    long_content = "这是一个很长的对话内容用来测试压缩功能。" * 400
    ctx = Context(
        system_prompt="You are a helpful assistant." * 100,
        messages=[{"role": "user", "content": long_content}],
        tool_results=[
            {"tool": "t1", "summary": "s1", "status": "ok"},
            {"tool": "t2", "summary": "s2", "status": "ok"},
        ],
    )
    assert ctx.token_count() > COMPACT_THRESHOLD
    result = await compact(ctx, mock_provider)
    # After compaction, tool_results should be cleared (their data is in summary)
    assert len(result.tool_results) == 0


async def test_micro_compression_on_append():
    """Tool result appended to context only keeps summary (micro-compression)."""
    ctx = Context(system_prompt="sys")
    ctx.append_tool_result("search", ToolResult(status="ok", summary="short summary", data={"large": "data" * 1000}))
    assert len(ctx.tool_results) == 1
    assert "data" not in ctx.tool_results[0]  # data field not stored in context


async def test_build_with_guest_user(mock_session_store):
    from app.auth.claims import Role, UserClaims

    guest = UserClaims(
        sub="g1",
        username="guest_user",
        role=Role.GUEST,
        pl="L1",
        dept=None,
        jti="jti-g",
    )
    ctx = await build("sess-g", "问题", guest)
    assert "L1" in ctx.system_prompt or "guest" in ctx.system_prompt.lower()


def test_build_rewrite_history_empty():
    from app.harness.context import build_rewrite_history
    from app.harness.models import Context

    ctx = Context(system_prompt="sp", messages=[{"role": "user", "content": "一个问题"}])
    result = build_rewrite_history(ctx)
    assert result == "无历史对话"


def test_build_rewrite_history_single_turn():
    from app.harness.context import build_rewrite_history
    from app.harness.models import Context

    ctx = Context(
        system_prompt="sp",
        messages=[
            {"role": "user", "content": "年假怎么申请？"},
            {"role": "assistant", "content": "根据员工手册，年假申请流程如下..."},
            {"role": "user", "content": "那病假呢？"},
        ],
    )
    result = build_rewrite_history(ctx)
    assert "年假怎么申请" in result
    assert "员工手册" in result
    assert "那病假呢" not in result  # 当前轮的用户消息不计入历史


def test_build_rewrite_history_truncates_assistant():
    from app.harness.context import build_rewrite_history
    from app.harness.models import Context

    long_answer = "非常详细" * 300  # > 200 chars
    ctx = Context(
        system_prompt="sp",
        messages=[
            {"role": "user", "content": "年假怎么申请？"},
            {"role": "assistant", "content": long_answer},
            {"role": "user", "content": "谢谢"},
        ],
    )
    result = build_rewrite_history(ctx)
    assert len(result) < len(long_answer) + 100  # 被截断


async def test_token_count_includes_system_prompt():
    ctx = Context(
        system_prompt="You are a helpful assistant specialized in enterprise knowledge base Q&A.",
        messages=[{"role": "user", "content": "测试问题"}],
    )
    tc = ctx.token_count()
    assert tc > 0
    # system_prompt alone is ~70 chars * 0.3 = ~21 tokens, message is ~4 chars * 0.3 = ~1 token
    # So total should be > 5
    assert tc > 5
