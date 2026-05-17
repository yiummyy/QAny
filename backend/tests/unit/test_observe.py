"""Unit tests for observe — structured observation extraction from tool results."""

from __future__ import annotations

import pytest

from app.harness.models import ObservationBlock, ToolResult
from app.harness.observe import observe


# ---------------------------------------------------------------------------
# search_knowledge — coverage verdicts
# ---------------------------------------------------------------------------


def _search_result(raw_hit: int, top_score: float, **kwargs) -> ToolResult:
    return ToolResult(
        status="ok",
        summary=f"search done: {raw_hit} hits, top={top_score}",
        data={
            "diagnostics": {
                "raw_hit_count": raw_hit,
                "rerank_top_score": top_score,
                "indexes_used": kwargs.get("indexes", ["qa_chunks"]),
            },
            "chunks": [{"id": f"c{i}"} for i in range(min(raw_hit, 5))],
        },
    )


def test_coverage_sufficient():
    obs = observe("search_knowledge", _search_result(20, 0.85), step=0)
    assert obs.coverage_verdict == "充足"
    assert obs.should_stop is False
    assert obs.suggested_action == ""


def test_coverage_moderate():
    obs = observe("search_knowledge", _search_result(8, 0.55), step=0)
    assert obs.coverage_verdict == "一般"
    assert obs.should_stop is False


def test_coverage_moderate_boundary_hit():
    """Exactly at threshold: hit=5, top=0.4 → 一般."""
    obs = observe("search_knowledge", _search_result(5, 0.4), step=0)
    assert obs.coverage_verdict == "一般"
    assert obs.should_stop is False


def test_coverage_insufficient_low_hits():
    obs = observe("search_knowledge", _search_result(3, 0.80), step=0)
    assert obs.coverage_verdict == "不足"


def test_coverage_insufficient_low_score():
    obs = observe("search_knowledge", _search_result(18, 0.30), step=0)
    assert obs.coverage_verdict == "不足"


# ---------------------------------------------------------------------------
# search_knowledge — zero results
# ---------------------------------------------------------------------------


def test_zero_results():
    obs = observe("search_knowledge", _search_result(0, 0.0), step=1)
    assert obs.coverage_verdict == "不足"
    assert obs.hit_count == 0
    assert "未找到" in obs.gap_description


# ---------------------------------------------------------------------------
# search_knowledge — degraded / stop signal
# ---------------------------------------------------------------------------


def test_search_degraded():
    result = ToolResult(
        status="degraded",
        summary="ES unreachable",
        data={"diagnostics": {"raw_hit_count": 0, "rerank_top_score": 0.0}},
    )
    obs = observe("search_knowledge", result, step=0)
    assert obs.should_stop is True
    assert "降级" in obs.stop_reason


# ---------------------------------------------------------------------------
# generate_answer
# ---------------------------------------------------------------------------


def test_generate_answer_ok():
    result = ToolResult(status="ok", summary="answer ready", data={})
    obs = observe("generate_answer", result, step=1)
    assert obs.answer_ready is True
    assert obs.quality_gate_passed is True
    assert obs.should_stop is False


def test_generate_answer_degraded():
    result = ToolResult(status="degraded", summary="all scores below 0.4", data={})
    obs = observe("generate_answer", result, step=1)
    assert obs.answer_ready is False
    assert obs.quality_gate_passed is False
    assert "兜底" in obs.gap_description


# ---------------------------------------------------------------------------
# generic / chitchat
# ---------------------------------------------------------------------------


def test_generic_tool():
    result = ToolResult(status="ok", summary="done", data={})
    obs = observe("hallucination_check", result, step=2)
    assert obs.tool_name == "hallucination_check"
    assert obs.should_stop is False


def test_generic_error():
    result = ToolResult(status="error", summary="timeout", data={})
    obs = observe("unknown_tool", result, step=0)
    assert obs.should_stop is True
    assert "执行失败" in obs.stop_reason
