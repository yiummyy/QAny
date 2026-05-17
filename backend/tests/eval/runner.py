#!/usr/bin/env python3
"""Enterprise QA MVP — Evaluation Runner (CI 快速回归).

Usage:
    python -m tests.eval.runner \\
        --eval-set tests/eval/eval_set.json \\
        --output report.json \\
        --base-url http://localhost:8000

Requires a running backend (or use --asgi to run with TestClient).

深度评估 (MRR/NDCG/MAP, QPS/TTFT, F1/ROUGE-L) 请使用:
    python -m tests.eval.cli retrieval | performance | quality | all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass
class EvalItem:
    id: str
    scene: str
    question: str
    expected_answer_keywords: list[str]
    relevant_doc_ids: list[str]
    min_sources: int = 1


@dataclass
class EvalResult:
    item: EvalItem
    answer: str = ""
    sources: list[dict] = field(default_factory=list)
    confidence: str = ""
    confidence_score: float = 0.0
    response_time_ms: int = 0
    trace_id: str = ""
    error: str = ""

    @property
    def expected_answer_keywords(self) -> list[str]:
        return self.item.expected_answer_keywords

    @property
    def relevant_doc_ids(self) -> list[str]:
        return self.item.relevant_doc_ids

    @property
    def min_sources(self) -> int:
        return self.item.min_sources

    @property
    def keyword_hit_count(self) -> int:
        if not self.answer:
            return 0
        text = self.answer.lower()
        return sum(1 for kw in self.expected_answer_keywords if kw.lower() in text)

    @property
    def keyword_hit_rate(self) -> float:
        if not self.expected_answer_keywords:
            return 1.0
        return self.keyword_hit_count / len(self.expected_answer_keywords)

    @property
    def recall_hit(self) -> bool:
        if not self.relevant_doc_ids or not self.sources:
            return len(self.relevant_doc_ids) == 0 and len(self.sources) >= self.min_sources
        source_ids = {s.get("doc_id", "") for s in self.sources}
        return bool(source_ids & set(self.relevant_doc_ids))

    @property
    def has_sufficient_sources(self) -> bool:
        return len(self.sources) >= self.min_sources


class EvalRunner:
    def __init__(self, base_url: str, token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(120.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def load_eval_set(path: str) -> list[EvalItem]:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items: list[EvalItem] = []
        for obj in raw["items"]:
            items.append(EvalItem(
                id=obj["id"],
                scene=obj["scene"],
                question=obj["question"],
                expected_answer_keywords=obj.get("expected_answer_keywords", []),
                relevant_doc_ids=obj.get("relevant_doc_ids", []),
                min_sources=obj.get("min_sources", 1),
            ))
        return items

    async def run_one(self, item: EvalItem) -> EvalResult:
        result = EvalResult(item=item)

        try:
            body = {
                "question": item.question,
                "session_id": f"eval_{item.id}",
                "scene": item.scene,
            }
            async with self.client.stream("POST", "/api/v1/qa/ask", json=body) as resp:
                if resp.status_code != 200:
                    result.error = f"HTTP {resp.status_code}"
                    return result

                buffer = ""
                async for chunk in resp.aiter_bytes():
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.rstrip("\r")
                        if line.startswith("event:"):
                            event_type = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data_str = line.split(":", 1)[1].strip()
                            self._process_event(event_type, data_str, result)

        except httpx.TimeoutException:
            result.error = "timeout"
        except httpx.ConnectError:
            result.error = "connection_refused"
        except Exception as e:
            result.error = str(e)[:200]

        return result

    def _process_event(self, event_type: str, data_str: str, result: EvalResult) -> None:
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            return

        if event_type == "done":
            result.answer = data.get("full_answer", "")
            result.sources = data.get("sources", [])
            result.confidence = data.get("confidence", "")
            result.confidence_score = data.get("confidence_score", 0.0)
            result.response_time_ms = data.get("response_time_ms", 0)
            result.trace_id = data.get("trace_id", "")
        elif event_type == "message":
            result.answer += data.get("chunk", "")
        elif event_type == "error" and not result.error:
            result.error = data.get("message", "unknown_error")
            result.answer = data.get("fallback_answer", "")


def compute_summary(results: list[EvalResult]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {"error": "no results"}

    success = [r for r in results if not r.error]
    fallback = [r for r in results if r.error and r.answer]

    keyword_hits = sum(1 for r in success if r.keyword_hit_rate >= 0.5)
    keyword_avg = sum(r.keyword_hit_rate for r in success) / len(success) if success else 0
    recall_hits = sum(1 for r in success if r.recall_hit)
    source_ok = sum(1 for r in success if r.has_sufficient_sources)
    avg_time = sum(r.response_time_ms for r in success) / len(success) if success else 0
    confidence_scores = [r.confidence_score for r in success if r.confidence_score > 0]

    by_scene: dict[str, dict] = {}
    for r in results:
        s = by_scene.setdefault(r.item.scene, {"total": 0, "keyword_ok": 0, "recall_ok": 0})
        s["total"] += 1
        if r.keyword_hit_rate >= 0.5:
            s["keyword_ok"] += 1
        if r.recall_hit:
            s["recall_ok"] += 1

    return {
        "total": total,
        "success": len(success),
        "errors": total - len(success),
        "fallbacks": len(fallback),
        "accuracy": round(keyword_hits / total, 4) if total else 0,
        "avg_keyword_hit_rate": round(keyword_avg, 4),
        "recall_at_k": round(recall_hits / total, 4) if total else 0,
        "source_sufficiency": round(source_ok / total, 4) if total else 0,
        "avg_response_time_ms": round(avg_time, 0),
        "avg_confidence": round(sum(confidence_scores) / len(confidence_scores), 4) if confidence_scores else 0,
        "by_scene": {
            s: {
                "total": d["total"],
                "accuracy": round(d["keyword_ok"] / d["total"], 4) if d["total"] else 0,
                "recall": round(d["recall_ok"] / d["total"], 4) if d["total"] else 0,
            }
            for s, d in by_scene.items()
        },
    }


def format_md_report(results: list[EvalResult], summary: dict) -> str:
    lines = [
        "# Evaluation Report",
        "",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total:** {summary['total']} | **Success:** {summary['success']} | **Errors:** {summary['errors']} | **Fallbacks:** {summary['fallbacks']}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Accuracy (keyword ≥50%) | {summary['accuracy']:.1%} |",
        f"| Avg Keyword Hit Rate | {summary['avg_keyword_hit_rate']:.1%} |",
        f"| Recall@K (source match) | {summary['recall_at_k']:.1%} |",
        f"| Source Sufficiency | {summary['source_sufficiency']:.1%} |",
        f"| Avg Response Time | {summary['avg_response_time_ms']:.0f}ms |",
        f"| Avg Confidence | {summary['avg_confidence']:.4f} |",
        "",
        "## By Scene",
        "",
        "| Scene | Total | Accuracy | Recall |",
        "|-------|-------|----------|--------|",
    ]
    for scene, d in summary.get("by_scene", {}).items():
        lines.append(f"| {scene} | {d['total']} | {d['accuracy']:.1%} | {d['recall']:.1%} |")

    lines += [
        "",
        "## Details",
        "",
        "| ID | Scene | Question | Keywords | Error | Time |",
        "|----|-------|----------|----------|-------|------|",
    ]
    for r in results:
        kw = f"{r.keyword_hit_count}/{len(r.expected_answer_keywords)}"
        err = r.error[:30] if r.error else "-"
        lines.append(f"| {r.item.id} | {r.item.scene} | {r.item.question[:30]}... | {kw} | {err} | {r.response_time_ms}ms |")

    return "\n".join(lines)


async def main() -> int:
    p = argparse.ArgumentParser(description="Enterprise QA MVP Evaluation Runner")
    p.add_argument("--eval-set", default="tests/eval/eval_set.json", help="Path to eval_set.json")
    p.add_argument("--output", default=None, help="Output JSON report path")
    p.add_argument("--md-report", default=None, help="Output Markdown report path")
    p.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    p.add_argument("--token", default="", help="JWT access token (bypass login)")
    p.add_argument("--limit", type=int, default=0, help="Limit to first N items")
    p.add_argument("--delay", type=float, default=0.5, help="Delay between questions (seconds)")
    args = p.parse_args()

    runner = EvalRunner(base_url=args.base_url, token=args.token)
    items = EvalRunner.load_eval_set(args.eval_set)
    if args.limit:
        items = items[:args.limit]

    print(f"Running {len(items)} evaluations against {args.base_url} ...")
    t0 = time.monotonic()

    results: list[EvalResult] = []
    for i, item in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] {item.id}: {item.question[:50]}...", end=" ")
        r = await runner.run_one(item)
        status = "OK" if not r.error else f"ERR({r.error[:20]})"
        print(f"{status} ({r.response_time_ms}ms)")
        results.append(r)
        if args.delay and i < len(items):
            await asyncio.sleep(args.delay)

    await runner.close()
    elapsed = time.monotonic() - t0

    summary = compute_summary(results)
    summary["elapsed_seconds"] = round(elapsed, 1)

    print(f"\nDone in {elapsed:.1f}s")
    print(f"Accuracy: {summary['accuracy']:.1%}  Recall: {summary['recall_at_k']:.1%}  "
          f"Success: {summary['success']}/{summary['total']}")

    if args.output:
        out = {
            "meta": {"timestamp": datetime.now().isoformat(), "base_url": args.base_url},
            "summary": summary,
            "results": [
                {
                    "id": r.item.id,
                    "scene": r.item.scene,
                    "question": r.item.question,
                    "answer": r.answer[:500],
                    "sources": r.sources,
                    "confidence": r.confidence,
                    "confidence_score": r.confidence_score,
                    "response_time_ms": r.response_time_ms,
                    "keyword_hit_rate": r.keyword_hit_rate,
                    "recall_hit": r.recall_hit,
                    "error": r.error,
                }
                for r in results
            ],
        }
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report → {args.output}")

    if args.md_report:
        md = format_md_report(results, summary)
        Path(args.md_report).write_text(md, encoding="utf-8")
        print(f"MD report → {args.md_report}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
