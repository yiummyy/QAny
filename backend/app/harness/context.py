"""Context assembly + three-tier compression — Spec §2.5, B4."""

from __future__ import annotations

import logging
from typing import Any

from app.auth.claims import UserClaims
from app.harness.models import Context
from app.harness.session_store import get_history

logger = logging.getLogger(__name__)

COMPACT_THRESHOLD = 3000
COMPACT_COOLDOWN_BASE = 2         # base cooldown steps for mild urgency
MIN_TOKEN_DELTA = 500             # minimum token growth before re-compacting
WORKING_MEMORY_MAX_MESSAGES = 20  # max messages in sliding window
WORKING_MEMORY_MIN_MESSAGES = 5   # min messages to retain during truncation


async def build(
    session_id: str,
    query: str,
    user_claims: UserClaims,
    system_prompt_override: str = "",
) -> Context:
    """Assemble context from session history + system prompt + current query."""
    history = await get_history(session_id)

    system_prompt = system_prompt_override or _build_system_prompt(user_claims)

    messages: list[dict[str, Any]] = []
    for record in history:
        if record.get("type") == "user":
            messages.append({"role": "user", "content": record.get("content", "")})
        elif record.get("type") == "assistant_stream":
            if messages and messages[-1]["role"] == "assistant":
                messages[-1]["content"] += record.get("chunk", "")
            else:
                messages.append({"role": "assistant", "content": record.get("chunk", "")})

    messages.append({"role": "user", "content": query})

    return Context(system_prompt=system_prompt, messages=messages)


async def compact(
    ctx: Context,
    provider_router: Any = None,
) -> Context:
    """Three-tier compaction when token count exceeds COMPACT_THRESHOLD.

    Tier 1 (light): Merge consecutive tool_result summaries (~15% savings).
    Tier 2 (medium): LLM summary of early messages (~40-60% savings).
                     Pinned constraints are preserved across compaction.
    Tier 3 (heavy): Truncation fallback — keep system prompt + summary + last K messages.
    """
    if ctx.token_count() <= COMPACT_THRESHOLD:
        return ctx

    # ---- Tier 1: Merge consecutive tool results ----
    _compact_merge_tool_results(ctx)
    if ctx.token_count() <= COMPACT_THRESHOLD:
        logger.debug("compact: tier 1 (merge) sufficient, tokens=%d", ctx.token_count())
        return ctx

    # ---- Tier 2: LLM summary of early history ----
    if provider_router is not None:
        summary = await _compact_summarize(ctx, provider_router)
        if summary:
            ctx._compacted_summary = summary
            ctx.tool_results.clear()
            # Keep only the last 3 messages
            if len(ctx.messages) > 3:
                ctx.messages = ctx.messages[-3:]
            if ctx.token_count() <= COMPACT_THRESHOLD:
                logger.debug("compact: tier 2 (LLM summary) sufficient, tokens=%d", ctx.token_count())
                return ctx
    else:
        # No LLM available — use heuristic truncation for summary
        conversation_text = _conversation_text(ctx)
        if len(conversation_text) > 2000:
            ctx._compacted_summary = "对话摘要: " + conversation_text[:2000] + "..."
        else:
            ctx._compacted_summary = "对话摘要: " + conversation_text
        ctx.tool_results.clear()
        if len(ctx.messages) > 3:
            ctx.messages = ctx.messages[-3:]

    # ---- Tier 3: Truncation fallback ----
    keep_count = max(WORKING_MEMORY_MIN_MESSAGES, int(len(ctx.messages) * 0.3))
    if len(ctx.messages) > keep_count:
        ctx.messages = ctx.messages[-keep_count:]
        logger.info("compact: tier 3 (truncation), kept=%d messages, tokens=%d", keep_count, ctx.token_count())

    return ctx


# ---------------------------------------------------------------------------
# Tier 1: Merge consecutive tool results
# ---------------------------------------------------------------------------


def _compact_merge_tool_results(ctx: Context) -> None:
    """Merge consecutive tool_result entries into combined summaries."""
    if len(ctx.tool_results) <= 1:
        return

    merged: list[dict[str, Any]] = []
    for tr in ctx.tool_results:
        if merged and merged[-1].get("tool") == tr.get("tool"):
            # Merge with previous same-tool result
            merged[-1]["summary"] = merged[-1]["summary"] + "; " + tr.get("summary", "")
        else:
            merged.append(dict(tr))
    ctx.tool_results = merged


# ---------------------------------------------------------------------------
# Tier 2: LLM summary of early history
# ---------------------------------------------------------------------------


async def _compact_summarize(ctx: Context, provider_router: Any) -> str | None:
    """Use LLM to summarize the oldest messages into a structured summary.

    If a previous summary exists, merge old + new information progressively.
    Pinned constraints are injected so the LLM does not discard them.
    """
    try:
        conversation_text = _conversation_text(ctx)
        previous = ctx._compacted_summary or ""

        # Build constraint note for the compaction prompt
        constraint_note = ""
        if ctx.pinned_constraints:
            constraint_note = "\n## 用户约束（不可丢弃）\n" + "\n".join(
                f"- [{c.constraint_type}] {c.constraint}" for c in ctx.pinned_constraints
            )

        if previous and previous != "对话摘要: ":
            prompt = (
                "以下是之前对话的结构化摘要：\n"
                f"{previous}\n\n"
                "以下是新增的对话内容，请将新旧信息合并为一份更新后的摘要：\n"
                f"{conversation_text[-3000:]}\n\n"
                "输出格式：\n"
                "- topics: 讨论的主题列表\n"
                "- key_facts: 用户提到的重要事实（去重合并）\n"
                "- unresolved: 尚未解决的问题（之前已解决则移除，新增则追加）\n"
                f"{constraint_note}\n"
                "请用中文输出简洁的JSON格式摘要（不超过300字）。"
            )
        else:
            prompt = (
                "将以下对话历史压缩为结构化摘要，保留关键信息：\n"
                "1. topics: 讨论的主题列表\n"
                "2. key_facts: 用户提到的重要事实（部门、角色、偏好等）\n"
                "3. unresolved: 尚未解决的问题\n\n"
                "对话历史:\n" + conversation_text[-3000:] + "\n\n"
                f"{constraint_note}\n"
                "请用中文输出简洁的JSON格式摘要（不超过200字）。"
            )

        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        result = await provider_router.chat(messages, stage="compaction", temperature=0.1, max_tokens=300)
        return f"[对话累积摘要] {result.strip()}"
    except Exception:
        logger.warning("compact: LLM summary failed, falling back to truncation")
        return None


def _conversation_text(ctx: Context) -> str:
    """Render conversation into plain text for summarization."""
    parts: list[str] = []
    for msg in ctx.messages:
        role = "用户" if msg["role"] == "user" else "助手"
        parts.append(f"{role}: {msg.get('content', '')}")
    for tr in ctx.tool_results:
        parts.append(f"[工具:{tr.get('tool', '')}] {tr.get('summary', '')}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Rewrite history builder
# ---------------------------------------------------------------------------


def build_rewrite_history(ctx, max_turns: int = 3) -> str:
    """Extract last N user/assistant turns as history text for rewrite."""
    turns: list[str] = []
    user_msg: str | None = None
    for msg in ctx.messages[-max_turns * 2 :]:
        if msg["role"] == "user":
            user_msg = msg.get("content", "")
        elif msg["role"] == "assistant" and user_msg is not None:
            assistant_text = msg.get("content", "")[:200]
            turns.append(f"用户: {user_msg}\n助手: {assistant_text}")
            user_msg = None
    return "\n".join(turns) if turns else "无历史对话"


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------


def _build_system_prompt(user_claims: UserClaims) -> str:
    role_name = {"admin": "管理员", "employee": "员工", "guest": "访客"}.get(
        user_claims.role.value, user_claims.role.value
    )
    return (
        f"你是企业知识库问答助手。当前用户角色: {role_name}，"
        f"权限级别: {user_claims.pl}。"
        f"请仅基于提供的参考文档回答用户问题，不得编造信息。"
        f"如果不确定答案，请直接说明。"
    )


# ---------------------------------------------------------------------------
# Adaptive compaction cooldown (Spec: context-compaction-optimization)
# ---------------------------------------------------------------------------


def should_compact(
    ctx: Context,
    last_compact_step: int,
    current_step: int,
    last_token_count: int = 0,
) -> bool:
    """Determine if compaction should trigger based on token urgency.

    Returns True when:
    - Token count exceeds COMPACT_THRESHOLD, AND
    - Cooldown has passed (adaptive: shorter for higher urgency), AND
    - Token growth since last check exceeds MIN_TOKEN_DELTA (unless severe).
    """
    current_tokens = ctx.token_count()
    if current_tokens <= COMPACT_THRESHOLD:
        return False

    steps_since = current_step - last_compact_step
    urgency = current_tokens / COMPACT_THRESHOLD

    # Determine cooldown based on urgency
    if urgency >= 2.0:
        cooldown = 0   # critical: compact immediately
    elif urgency >= 1.5:
        cooldown = 0   # severe: compact immediately
    elif urgency >= 1.2:
        cooldown = 1   # moderate: wait 1 step
    else:
        cooldown = COMPACT_COOLDOWN_BASE  # mild: normal cooldown

    if steps_since < cooldown:
        return False

    # Avoid re-compacting when token count is barely growing
    if urgency < 1.5 and last_token_count > 0:
        delta = current_tokens - last_token_count
        if delta < MIN_TOKEN_DELTA:
            return False

    return True
