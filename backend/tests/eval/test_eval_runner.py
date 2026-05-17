"""Unit tests for eval runner logic (no live backend required)."""

import json
from pathlib import Path

import pytest
from tests.eval.runner import EvalItem, EvalResult, compute_summary, EvalRunner, format_md_report


def _make_result(
    eid: str = "eval_001",
    scene: str = "policy",
    answer: str = "",
    keywords: list[str] | None = None,
    sources: list[dict] | None = None,
    relevant_ids: list[str] | None = None,
    error: str = "",
) -> EvalResult:
    item = EvalItem(
        id=eid,
        scene=scene,
        question="test question",
        expected_answer_keywords=keywords or [],
        relevant_doc_ids=relevant_ids or [],
        min_sources=1,
    )
    return EvalResult(
        item=item,
        answer=answer,
        sources=sources or [],
        error=error,
    )


class TestEvalItemKeywords:
    def test_all_keywords_hit(self) -> None:
        r = _make_result(answer="公司年假根据工龄天数计算", keywords=["年假", "工龄", "天数"])
        assert r.keyword_hit_count == 3
        assert r.keyword_hit_rate == 1.0

    def test_partial_keywords(self) -> None:
        r = _make_result(answer="年假是根据工龄确定的", keywords=["年假", "工龄", "天数"])
        assert r.keyword_hit_count == 2
        assert r.keyword_hit_rate == 2 / 3

    def test_no_keywords(self) -> None:
        r = _make_result(answer="这个我不清楚", keywords=["年假", "工龄"])
        assert r.keyword_hit_count == 0
        assert r.keyword_hit_rate == 0.0

    def test_empty_keywords_always_hit(self) -> None:
        r = _make_result(answer="任何答案", keywords=[])
        assert r.keyword_hit_rate == 1.0

    def test_case_insensitive(self) -> None:
        r = _make_result(answer="公司年假制度", keywords=["年假"])
        assert r.keyword_hit_count == 1

    def test_error_result_zero_hit(self) -> None:
        r = _make_result(answer="", keywords=["年假"], error="timeout")
        assert r.keyword_hit_rate == 0.0


class TestEvalResultRecall:
    def test_source_match(self) -> None:
        r = _make_result(
            sources=[{"doc_id": "doc_handbook"}],
            relevant_ids=["doc_handbook"],
        )
        assert r.recall_hit is True

    def test_source_no_match(self) -> None:
        r = _make_result(
            sources=[{"doc_id": "doc_other"}],
            relevant_ids=["doc_handbook"],
        )
        assert r.recall_hit is False

    def test_no_relevant_ids_with_sources(self) -> None:
        r = _make_result(
            sources=[{"doc_id": "doc_1"}],
            relevant_ids=[],
        )
        assert r.recall_hit is True

    def test_no_sources(self) -> None:
        r = _make_result(sources=[], relevant_ids=["doc_handbook"])
        assert r.recall_hit is False

    def test_source_sufficiency(self) -> None:
        item = EvalItem(
            id="eval_001", scene="test", question="q",
            expected_answer_keywords=[], relevant_doc_ids=[], min_sources=2,
        )
        r = EvalResult(item=item, sources=[{"doc_id": "d1"}])
        assert r.has_sufficient_sources is False
        r2 = EvalResult(item=item, sources=[{"doc_id": "d1"}, {"doc_id": "d2"}])
        assert r2.has_sufficient_sources is True


class TestComputeSummary:
    def test_empty(self) -> None:
        s = compute_summary([])
        assert "error" in s

    def test_all_success(self) -> None:
        results = [
            _make_result("e1", answer="年假工龄天数计算", keywords=["年假", "工龄", "天数"],
                        sources=[{"doc_id": "doc_1"}], relevant_ids=["doc_1"]),
            _make_result("e2", answer="报销流程需要提交发票", keywords=["报销", "流程"],
                        sources=[{"doc_id": "doc_2"}], relevant_ids=["doc_2"]),
        ]
        s = compute_summary(results)
        assert s["success"] == 2
        assert s["errors"] == 0
        assert s["accuracy"] == 1.0
        assert s["recall_at_k"] == 1.0

    def test_mixed_results(self) -> None:
        results = [
            _make_result("e1", answer="correct answer here", keywords=["correct"],
                        sources=[{"doc_id": "x"}], relevant_ids=["x"]),
            _make_result("e2", answer="wrong", keywords=["correct"], error="timeout",
                        sources=[], relevant_ids=["y"]),
        ]
        s = compute_summary(results)
        assert s["success"] == 1
        assert s["errors"] == 1
        assert s["accuracy"] == 0.5  # only e1 passes keyword threshold
        assert s["recall_at_k"] == 0.5

    def test_by_scene_breakdown(self) -> None:
        results = [
            _make_result("e1", scene="policy", answer="ans", keywords=["a"],
                        sources=[{"doc_id": "d1"}], relevant_ids=["d1"]),
            _make_result("e2", scene="policy", answer="bad", keywords=["correct"]),
            _make_result("e3", scene="product", answer="ans", keywords=["a"],
                        sources=[{"doc_id": "d1"}], relevant_ids=["d1"]),
        ]
        s = compute_summary(results)
        assert "policy" in s["by_scene"]
        assert "product" in s["by_scene"]
        assert s["by_scene"]["policy"]["accuracy"] == 0.5
        assert s["by_scene"]["product"]["accuracy"] == 1.0


class TestEvalSetJson:
    def test_load_eval_set(self) -> None:
        path = Path(__file__).parent / "eval_set.json"
        assert path.exists(), "eval_set.json not found"
        items = EvalRunner.load_eval_set(str(path))
        assert len(items) == 50
        scenes = {i.scene for i in items}
        assert scenes == {"policy", "process", "product", "troubleshoot", "training"}
        for item in items:
            assert item.id, f"Item missing id"
            assert item.question, f"Item {item.id} missing question"
            assert item.scene in scenes, f"Item {item.id} invalid scene"

    def test_scene_counts(self) -> None:
        path = Path(__file__).parent / "eval_set.json"
        items = EvalRunner.load_eval_set(str(path))
        from collections import Counter
        counts = Counter(i.scene for i in items)
        for scene, count in counts.items():
            assert count == 10, f"Expected 10 items for {scene}, got {count}"


class TestFormatMdReport:
    def test_generates_report(self) -> None:
        results = [
            _make_result("e1", scene="policy", answer="ans", keywords=["a"]),
        ]
        summary = compute_summary(results)
        md = format_md_report(results, summary)
        assert "# Evaluation Report" in md
        assert "e1" in md
        assert "policy" in md
