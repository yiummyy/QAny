"""报告生成 — JSON 结构化数据 + Markdown 可读报告."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def retrieval_to_dict(report: Any) -> dict[str, Any]:
    return {
        "summary": {
            "total_queries": report.total_queries,
            "errors": report.errors,
            "mrr_raw_10_avg": round(report.mrr_raw_10_avg, 4),
            "mrr_rerank_5_avg": round(report.mrr_rerank_5_avg, 4),
            "ndcg_raw_10_avg": round(report.ndcg_raw_10_avg, 4),
            "ndcg_rerank_5_avg": round(report.ndcg_rerank_5_avg, 4),
            "map_raw_10_avg": round(report.map_raw_10_avg, 4),
            "map_rerank_5_avg": round(report.map_rerank_5_avg, 4),
            "recall_raw_10_avg": round(report.recall_raw_10_avg, 4),
            "recall_rerank_5_avg": round(report.recall_rerank_5_avg, 4),
        },
        "details": [
            {
                "id": pq.item_id,
                "mrr_raw10": pq.mrr_raw_10,
                "mrr_rerank5": pq.mrr_rerank_5,
                "ndcg_raw10": pq.ndcg_raw_10,
                "ndcg_rerank5": pq.ndcg_rerank_5,
                "map_raw10": pq.map_raw_10,
                "map_rerank5": pq.map_rerank_5,
                "error": pq.error,
            }
            for pq in report.per_query
        ],
    }


def retrieval_md(report: Any) -> str:
    lines = [
        "# Retrieval Evaluation Report",
        f"**Date:** {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"**Queries:** {report.total_queries} | **Errors:** {report.errors}",
        "",
        "## Summary",
        "",
        "| Metric | Raw (Top-20, before Rerank) | Rerank (Top-5) |",
        "|--------|---------------------------|----------------|",
        f"| MRR    | {report.mrr_raw_10_avg:.4f} | {report.mrr_rerank_5_avg:.4f} |",
        f"| NDCG   | {report.ndcg_raw_10_avg:.4f} | {report.ndcg_rerank_5_avg:.4f} |",
        f"| MAP    | {report.map_raw_10_avg:.4f} | {report.map_rerank_5_avg:.4f} |",
        f"| Recall | {report.recall_raw_10_avg:.4f} | {report.recall_rerank_5_avg:.4f} |",
        "",
        "## Per-Query Detail",
        "",
        "| ID | MRR(raw) | NDCG(raw) | MAP(raw) | MRR(rerank) | NDCG(rerank) | MAP(rerank) |",
        "|----|----------|-----------|----------|-------------|--------------|-------------|",
    ]
    for pq in report.per_query:
        if pq.error:
            lines.append(f"| {pq.item_id} | ! {pq.error[:30]} |")
        else:
            lines.append(
                f"| {pq.item_id} | {pq.mrr_raw_10:.3f} | {pq.ndcg_raw_10:.3f} | {pq.map_raw_10:.3f} | "
                f"{pq.mrr_rerank_5:.3f} | {pq.ndcg_rerank_5:.3f} | {pq.map_rerank_5:.3f} |"
            )
    return "\n".join(lines)


def perf_to_dict(report: Any) -> dict[str, Any]:
    return {"concurrency_levels": report.concurrency_levels}


def perf_md(report: Any) -> str:
    lines = [
        "# Performance Benchmark Report",
        f"**Date:** {datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "## Latency vs Concurrency",
        "",
        "| Concurrency | QPS | TTFT P50 | TTFT P99 | Total P50 | Total P99 | Success Rate |",
        "|-------------|-----|----------|----------|-----------|-----------|--------------|",
    ]
    for _, stats in sorted(report.concurrency_levels.items()):
        lines.append(
            f"| {stats['concurrency']} "
            f"| {stats.get('qps', '-')} "
            f"| {stats.get('ttft_p50_ms', '-')}ms "
            f"| {stats.get('ttft_p99_ms', '-')}ms "
            f"| {stats.get('total_p50_ms', '-')}ms "
            f"| {stats.get('total_p99_ms', '-')}ms "
            f"| {stats.get('success_rate', '-')} |"
        )

    ttft_values = [s.ttft_ms for s in report.raw_samples if s.ttft_ms > 0]
    if ttft_values:
        from tests.eval.performance import percentile
        lines += [
            "",
            "## TTFT Distribution",
            "",
            f"- **Min:** {min(ttft_values):.0f}ms",
            f"- **P50:** {percentile(ttft_values, 50):.0f}ms",
            f"- **P95:** {percentile(ttft_values, 95):.0f}ms",
            f"- **P99:** {percentile(ttft_values, 99):.0f}ms",
            f"- **Max:** {max(ttft_values):.0f}ms",
        ]

    return "\n".join(lines)


def quality_to_dict(report: Any) -> dict[str, Any]:
    return {
        "summary": {
            "total_queries": report.total_queries,
            "errors": report.errors,
            "f1_avg": round(report.f1_avg, 4),
            "em_rate": report.em_rate,
            "rouge_l_avg": report.rouge_l_avg,
            "factual_accuracy": report.factual_accuracy,
        },
        "by_scene": report.by_scene,
        "details": [
            {
                "id": pq.item_id,
                "answer_short": pq.answer_short,
                "f1": pq.f1,
                "exact_match": pq.exact_match,
                "rouge_l": pq.rouge_l,
                "factual_passed": pq.factual_passed,
                "response_time_ms": pq.response_time_ms,
                "confidence_score": pq.confidence_score,
                "error": pq.error,
            }
            for pq in report.per_query
        ],
    }


def quality_md(report: Any) -> str:
    lines = [
        "# Answer Quality Evaluation Report",
        f"**Date:** {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"**Queries:** {report.total_queries} | **Errors:** {report.errors}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Token F1 (avg) | {report.f1_avg:.4f} |",
        f"| Exact Match Rate | {report.em_rate:.1%} |",
        f"| ROUGE-L (avg) | {report.rouge_l_avg:.4f} |",
        f"| Factual Accuracy | {report.factual_accuracy:.1%} |",
        "",
    ]

    if report.by_scene:
        lines += [
            "## By Scene",
            "",
            "| Scene | Count | F1 Avg | EM Rate | Factual |",
            "|-------|-------|--------|---------|---------|",
        ]
        for scene, stats in report.by_scene.items():
            lines.append(
                f"| {scene} | {stats['count']} | {stats['f1_avg']:.4f} | "
                f"{stats['em_rate']:.1%} | {stats['factual_accuracy']:.1%} |"
            )
        lines.append("")

    lines += [
        "## Per-Query Detail",
        "",
        "| ID | F1 | EM | ROUGE-L | Factual | Time(ms) | Confidence |",
        "|----|----|----|---------|---------|----------|------------|",
    ]
    for pq in report.per_query:
        if pq.status != "success":
            lines.append(f"| {pq.item_id} | ! {pq.error[:40]} |")
        else:
            lines.append(
                f"| {pq.item_id} | {pq.f1:.3f} | {'v' if pq.exact_match else ''} | "
                f"{pq.rouge_l:.3f} | {'v' if pq.factual_passed else ''} | "
                f"{pq.response_time_ms:.0f} | {pq.confidence_score:.3f} |"
            )
    return "\n".join(lines)


def write_report(data: dict[str, Any], json_path: str, md_path: str | None, md_content: str):
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if md_path:
        Path(md_path).parent.mkdir(parents=True, exist_ok=True)
        Path(md_path).write_text(md_content, encoding="utf-8")
