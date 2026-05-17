"""Observe phase — extract structured quality signals from tool results.

Part of the Agent ReAct loop: programmatic observation that informs Plan decisions
without relying on the Plan LLM to infer quality from raw summary text.
"""

from __future__ import annotations

from typing import Any

from app.harness.models import ObservationBlock, ToolResult

# ---------------------------------------------------------------------------
# Quality thresholds (aligned with existing MIN_SCORE_THRESHOLD=0.4 and
# eval_set baselines: healthy >=15 hits, >=0.7 rerank_top_score)
# ---------------------------------------------------------------------------

_COVERAGE_HIT_THRESHOLD = 15    # raw_hit_count >= this → candidate for "充足"
_COVERAGE_SCORE_THRESHOLD = 0.7  # rerank_top_score >= this → candidate for "充足"
_MIN_HIT_THRESHOLD = 5          # raw_hit_count >= this → candidate for "一般"
_MIN_SCORE_THRESHOLD = 0.4      # rerank_top_score >= this → candidate for "一般"


def observe(tool_name: str, result: ToolResult, step: int) -> ObservationBlock:
    """Extract structured observation from a tool execution result.

    Dispatches to the appropriate handler based on tool_name.
    """
    if tool_name in ("search_knowledge", "query_knowledge"):
        return _observe_search(result, step)
    if tool_name == "generate_answer":
        return _observe_generate(result, step)
    return _observe_generic(tool_name, result, step)


# ---------------------------------------------------------------------------
# search_knowledge observer
# ---------------------------------------------------------------------------


def _observe_search(result: ToolResult, step: int) -> ObservationBlock:
    data = result.data or {}
    diag = data.get("diagnostics", {})
    raw_hit = diag.get("raw_hit_count", 0)
    top_score = diag.get("rerank_top_score", 0.0)
    chunks = data.get("chunks", [])
    indexes = diag.get("indexes_used", [])

    # ---- programmatic quality assessment ----
    if raw_hit >= _COVERAGE_HIT_THRESHOLD and top_score >= _COVERAGE_SCORE_THRESHOLD:
        coverage = "充足"
    elif raw_hit >= _MIN_HIT_THRESHOLD and top_score >= _MIN_SCORE_THRESHOLD:
        coverage = "一般"
    else:
        coverage = "不足"

    # ---- gap description ----
    if coverage == "不足":
        if raw_hit == 0:
            gap = "知识库中未找到相关内容"
        else:
            gap = "检索结果可能无法完整回答用户问题"
    elif not chunks:
        gap = "知识库中未找到相关内容"
    else:
        gap = ""

    # ---- suggested action ----
    if coverage == "充足":
        action = ""
    elif coverage == "一般":
        action = "检索质量中等，建议优先使用已有结果；如需更精准答案可考虑重搜"
    else:
        idx_label = ", ".join(indexes) if indexes else "默认索引"
        action = f"检索质量不足，建议用更宽泛关键词重搜 {idx_label}"

    # ---- stop signal: zero results AND already degraded ----
    should_stop = (
        result.status == "degraded"
        or (raw_hit == 0 and coverage == "不足")
    )
    stop_reason = ""
    if should_stop:
        if result.status == "degraded":
            stop_reason = "检索服务降级，无法获取有效结果"
        elif raw_hit == 0:
            stop_reason = "知识库中未找到相关内容"

    return ObservationBlock(
        step=step,
        tool_name="search_knowledge",
        status=result.status,
        should_stop=should_stop,
        stop_reason=stop_reason,
        hit_count=raw_hit,
        top_score=top_score,
        coverage_verdict=coverage,
        indexes_searched=indexes,
        gap_description=gap,
        suggested_action=action,
    )


# ---------------------------------------------------------------------------
# generate_answer observer
# ---------------------------------------------------------------------------


def _observe_generate(result: ToolResult, step: int) -> ObservationBlock:
    degraded = result.status == "degraded"
    return ObservationBlock(
        step=step,
        tool_name="generate_answer",
        status=result.status,
        should_stop=False,  # generate_answer's degrade is handled upstream in _stream_final_answer
        stop_reason="",
        answer_ready=not degraded,
        quality_gate_passed=not degraded,
        gap_description="检索相关度不足，已返回兜底回答" if degraded else "",
        suggested_action="" if not degraded else "建议用户查阅原始文档或咨询相关部门",
    )


# ---------------------------------------------------------------------------
# generic / fallback observer
# ---------------------------------------------------------------------------


def _observe_generic(tool_name: str, result: ToolResult, step: int) -> ObservationBlock:
    return ObservationBlock(
        step=step,
        tool_name=tool_name,
        status=result.status,
        should_stop=result.status in ("error",),
        stop_reason=f"{tool_name} 执行失败: {result.summary}" if result.status == "error" else "",
    )
