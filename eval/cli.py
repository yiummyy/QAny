"""统一 CLI — eval retrieval / performance / quality / all.

Usage:
    python -m eval retrieval  --eval-set eval/data/eval_set_v2.json
    python -m eval performance --eval-set eval/data/eval_set_v2.json --concurrency 1,5,10
    python -m eval quality     --eval-set eval/data/eval_set_v2.json --base-url http://localhost:8000
    python -m eval all         --eval-set eval/data/eval_set_v2.json --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from eval.dataset import load_eval_set, validate_eval_set
from eval.performance import benchmark_concurrency
from eval.quality import QualityEvaluator
from eval.reporter import (
    perf_md,
    perf_to_dict,
    quality_md,
    quality_to_dict,
    retrieval_md,
    retrieval_to_dict,
    write_report,
)
from eval.retrieval import RetrievalEvaluator


def _parse_concurrency(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",")]


# ── 子命令 ───────────────────────────────────────────


async def cmd_retrieval(args) -> int:
    items = load_eval_set(args.eval_set)
    if args.limit:
        items = items[: args.limit]

    print(f"Evaluating retrieval on {len(items)} queries (mode={args.mode}) ...")
    t0 = time.monotonic()

    evaluator = RetrievalEvaluator(mode=args.mode, base_url=args.base_url)
    report = await evaluator.evaluate(items)

    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.1f}s")
    print(f"  MRR  raw@10={report.mrr_raw_10_avg:.4f}  rerank@5={report.mrr_rerank_5_avg:.4f}")
    print(f"  NDCG raw@10={report.ndcg_raw_10_avg:.4f}  rerank@5={report.ndcg_rerank_5_avg:.4f}")
    print(f"  MAP  raw@10={report.map_raw_10_avg:.4f}  rerank@5={report.map_rerank_5_avg:.4f}")

    data = retrieval_to_dict(report)
    data["meta"] = {"mode": args.mode, "elapsed_seconds": round(elapsed, 1)}
    write_report(
        data,
        args.output or "reports/retrieval.json",
        args.md_output or "reports/retrieval.md",
        retrieval_md(report),
    )
    return 0


async def cmd_performance(args) -> int:
    items = load_eval_set(args.eval_set)
    if args.limit:
        items = items[: args.limit]

    levels = _parse_concurrency(args.concurrency)
    print(f"Benchmarking performance: {len(items)} queries, concurrency={levels} ...")
    t0 = time.monotonic()

    report = await benchmark_concurrency(args.base_url, items, levels, token=args.token)

    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.1f}s")
    for _, stats in sorted(report.concurrency_levels.items()):
        print(
            f"  concurrency={stats['concurrency']:>3}  "
            f"QPS={stats.get('qps', 0):>6.1f}  "
            f"TTFT_p50={stats.get('ttft_p50_ms', 0):>6.0f}ms  "
            f"Success={stats.get('success_rate', 0):.1%}"
        )

    data = perf_to_dict(report)
    data["meta"] = {"elapsed_seconds": round(elapsed, 1)}
    write_report(
        data,
        args.output or "reports/performance.json",
        args.md_output or "reports/performance.md",
        perf_md(report),
    )
    return 0


async def cmd_quality(args) -> int:
    items = load_eval_set(args.eval_set)
    if args.limit:
        items = items[: args.limit]

    # 校验标注完整性
    val = validate_eval_set(items)
    print(f"Dataset: {val['total']} items")
    print(f"  with relevance_judgments: {val['with_relevance_judgments']}")
    print(f"  with ground_truth_answer: {val['with_ground_truth']}")
    if val["missing_ground_truth"]:
        print(f"  WARNING: {len(val['missing_ground_truth'])} items missing ground_truth_answer — F1/EM/ROUGE-L will be 0")

    print(f"\nEvaluating answer quality on {len(items)} queries ...")
    t0 = time.monotonic()

    evaluator = QualityEvaluator(base_url=args.base_url, token=args.token)
    report = await evaluator.evaluate(items)

    elapsed = time.monotonic() - t0
    print(f"Done in {elapsed:.1f}s")
    print(f"  F1={report.f1_avg:.4f}  EM={report.em_rate:.1%}  "
          f"ROUGE-L={report.rouge_l_avg:.4f}  Factual={report.factual_accuracy:.1%}")

    data = quality_to_dict(report)
    data["meta"] = {"elapsed_seconds": round(elapsed, 1)}
    write_report(
        data,
        args.output or "reports/quality.json",
        args.md_output or "reports/quality.md",
        quality_md(report),
    )
    return 0


async def cmd_all(args) -> int:
    items = load_eval_set(args.eval_set)
    if args.limit:
        items = items[: args.limit]

    print(f"=== QAny Full Evaluation Suite ===\n")
    print(f"Dataset: {len(items)} items | Base URL: {args.base_url}\n")

    all_data: dict[str, dict] = {}

    # 1. Retrieval
    print("─" * 50)
    print("[1/3] Retrieval Evaluation ...")
    ret_eval = RetrievalEvaluator(mode="direct")
    ret_report = await ret_eval.evaluate(items)
    print(f"  MRR(raw@10)={ret_report.mrr_raw_10_avg:.4f}  NDCG(raw@10)={ret_report.ndcg_raw_10_avg:.4f}  "
          f"MAP(rerank@5)={ret_report.map_rerank_5_avg:.4f}")
    all_data["retrieval"] = retrieval_to_dict(ret_report)

    # 2. Performance
    print("[2/3] Performance Benchmark ...")
    perf_report = await benchmark_concurrency(
        args.base_url, items, _parse_concurrency(args.concurrency), token=args.token
    )
    for _, stats in sorted(perf_report.concurrency_levels.items()):
        print(f"  c={stats['concurrency']}  QPS={stats.get('qps',0):.1f}  "
              f"TTFT_p50={stats.get('ttft_p50_ms',0):.0f}ms")
    all_data["performance"] = perf_to_dict(perf_report)

    # 3. Quality
    print("[3/3] Answer Quality Evaluation ...")
    qual_eval = QualityEvaluator(base_url=args.base_url, token=args.token)
    qual_report = await qual_eval.evaluate(items)
    print(f"  F1={qual_report.f1_avg:.4f}  EM={qual_report.em_rate:.1%}  "
          f"Factual={qual_report.factual_accuracy:.1%}")
    all_data["quality"] = quality_to_dict(qual_report)

    # 统一输出
    out_dir = args.output_dir or "reports"
    ts = time.strftime("%Y%m%d_%H%M%S")

    # JSON
    json_path = f"{out_dir}/full_{ts}.json"
    Path(json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(json_path).write_text(
        json.dumps(all_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nFull JSON report → {json_path}")

    # Markdown
    md_path = f"{out_dir}/full_{ts}.md"
    md_parts = [
        retrieval_md(ret_report),
        "\n---\n",
        perf_md(perf_report),
        "\n---\n",
        quality_md(qual_report),
    ]
    Path(md_path).write_text("\n".join(md_parts), encoding="utf-8")
    print(f"Full MD report   → {md_path}")

    return 0


# ── 入口 ─────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="QAny Evaluation Toolkit — 检索/性能/质量 三维评估"
    )
    sub = parser.add_subparsers(dest="command", help="评估类型")

    # ---- retrieval ----
    p_ret = sub.add_parser("retrieval", help="检索质量评估 (MRR/NDCG/MAP)")
    p_ret.add_argument("--eval-set", default="eval/data/eval_set_v2.json")
    p_ret.add_argument("--mode", default="direct", choices=["direct", "api"])
    p_ret.add_argument("--base-url", default="http://localhost:8000")
    p_ret.add_argument("--limit", type=int, default=0)
    p_ret.add_argument("--output")
    p_ret.add_argument("--md-output")

    # ---- performance ----
    p_perf = sub.add_parser("performance", help="系统性能压测 (QPS/TTFT/延迟分位数)")
    p_perf.add_argument("--eval-set", default="eval/data/eval_set_v2.json")
    p_perf.add_argument("--base-url", default="http://localhost:8000")
    p_perf.add_argument("--concurrency", default="1,5,10,20")
    p_perf.add_argument("--token", default="")
    p_perf.add_argument("--limit", type=int, default=0)
    p_perf.add_argument("--output")
    p_perf.add_argument("--md-output")

    # ---- quality ----
    p_qual = sub.add_parser("quality", help="模型生成质量评估 (F1/EM/ROUGE-L/Factual)")
    p_qual.add_argument("--eval-set", default="eval/data/eval_set_v2.json")
    p_qual.add_argument("--base-url", default="http://localhost:8000")
    p_qual.add_argument("--token", default="")
    p_qual.add_argument("--limit", type=int, default=0)
    p_qual.add_argument("--output")
    p_qual.add_argument("--md-output")

    # ---- all ----
    p_all = sub.add_parser("all", help="一键全量评估")
    p_all.add_argument("--eval-set", default="eval/data/eval_set_v2.json")
    p_all.add_argument("--base-url", default="http://localhost:8000")
    p_all.add_argument("--concurrency", default="1,5,10")
    p_all.add_argument("--token", default="")
    p_all.add_argument("--limit", type=int, default=0)
    p_all.add_argument("--output-dir", default="reports")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    return asyncio.run(_dispatch(args))


async def _dispatch(args) -> int:
    if args.command == "retrieval":
        return await cmd_retrieval(args)
    if args.command == "performance":
        return await cmd_performance(args)
    if args.command == "quality":
        return await cmd_quality(args)
    if args.command == "all":
        return await cmd_all(args)
    return 1
