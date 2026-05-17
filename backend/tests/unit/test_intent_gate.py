"""Unit tests for intent_gate — chitchat short-circuit logic."""

from __future__ import annotations

import pytest

from app.tools.intent_gate import (
    CAPABILITY_GUIDE,
    FAREWELL_RESPONSE,
    GREETING_RESPONSE,
    IDENTITY_RESPONSE,
    THANKS_RESPONSE,
    check,
)


# ---------------------------------------------------------------------------
# Greeting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["你好", "您好", "hi", "hello", "嗨", "早上好", "下午好", "晚上好", "在吗"])
def test_greeting_blocked(query: str):
    result = check(query, intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "greeting"
    assert result.response == GREETING_RESPONSE


# ---------------------------------------------------------------------------
# Thanks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["谢谢", "感谢", "多谢", "thanks", "thank you"])
def test_thanks_blocked(query: str):
    result = check(query, intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "thanks"
    assert result.response == THANKS_RESPONSE


# ---------------------------------------------------------------------------
# Farewell
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["再见", "拜拜", "bye", "回头见", "晚安"])
def test_farewell_blocked(query: str):
    result = check(query, intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "farewell"
    assert result.response == FAREWELL_RESPONSE


# ---------------------------------------------------------------------------
# Out of scope
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", [
    "今天天气怎么样",
    "给我讲个笑话",
    "帮我写一首诗",
    "今天心情不错",
])
def test_out_of_scope_blocked(query: str):
    result = check(query, intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "out_of_scope"
    assert result.response == CAPABILITY_GUIDE


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["你是谁", "你叫什么", "你的名字", "who are you"])
def test_identity_blocked(query: str):
    result = check(query, intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "identity"
    assert result.response == IDENTITY_RESPONSE


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["你会什么", "你能做什么", "你能干什么", "你有什么功能", "你怎么用"])
def test_capability_blocked(query: str):
    result = check(query, intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "capability"
    assert result.response == CAPABILITY_GUIDE


# ---------------------------------------------------------------------------
# Pass-through: genuine knowledge queries must NOT be blocked
# ---------------------------------------------------------------------------


def test_knowledge_query_passes_through():
    """A real knowledge query with a recognized intent is not blocked."""
    result = check("年假怎么算", intent="制度查询", entities=["年假"], tags=["入职须知"])
    assert result is None


def test_other_with_entities_passes_through():
    """Intent=其他 but with entities means something was extracted — let it search."""
    result = check("那个怎么申请", intent="其他", entities=["OA系统"], tags=[])
    assert result is None


def test_other_with_tags_passes_through():
    """Intent=其他 but with tags means the LLM predicted a relevant tag — let it search."""
    result = check("怎么处理", intent="其他", entities=[], tags=["网络故障"])
    assert result is None


def test_other_no_signal_but_not_matching_pattern():
    """A vague query that matches no chitchat pattern → out_of_scope."""
    result = check("这是什么", intent="其他", entities=[], tags=[])
    assert result is not None
    assert result.blocked is True
    assert result.category == "out_of_scope"


# ---------------------------------------------------------------------------
# P0: rewrite_failed pass-through
# ---------------------------------------------------------------------------


def test_rewrite_failed_passes_through():
    """When rewrite LLM failed, Gate must NOT block — let RAG proceed."""
    result = check("你好", intent="其他", entities=[], tags=[], rewrite_failed=True)
    assert result is None


def test_rewrite_failed_overrides_gate_chitchat():
    """Even a clear greeting must pass through when rewrite failed."""
    result = check("你好", intent="其他", entities=[], tags=["网络故障"], rewrite_failed=True)
    assert result is None


# ---------------------------------------------------------------------------
# P2: Weak signal pass-through (rewritten ≠ query)
# ---------------------------------------------------------------------------


def test_rewritten_diff_passes_through():
    """LLM did coreference resolution — signal found, let it through."""
    result = check(
        "那个怎么填", intent="其他", entities=[], tags=[],
        rewritten_query="员工手册怎么填",
    )
    assert result is None


def test_rewritten_diff_with_whitespace():
    """Trimming should normalize — if only whitespace differs, still gate."""
    result = check(
        " 你好 ", intent="其他", entities=[], tags=[],
        rewritten_query="你好",
    )
    assert result is not None
    assert result.category == "greeting"


def test_rewritten_same_passes_gate():
    """When rewritten equals original, normal gate logic applies."""
    result = check("你好", intent="其他", entities=[], tags=[], rewritten_query="你好")
    assert result is not None
    assert result.category == "greeting"
