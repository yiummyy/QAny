"""系统性能评估 — QPS / TTFT / 总响应时间 / 延迟分位数.

通过异步并发 SSE 流解析实现精确的 TTFT（Time To First Token）测量.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import httpx

from tests.eval.dataset import EvalItemV2


@dataclass
class PerfSample:
    """单次请求的性能剖面."""

    item_id: str = ""
    ttft_ms: float = 0.0
    total_ms: float = 0.0
    token_count: int = 0
    status: str = "success"
    error: str = ""


def percentile(values: list[float], p: float) -> float:
    """计算 p-th 百分位数（线性插值）."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (p / 100.0) * (len(sorted_vals) - 1)
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_vals):
        return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
    return sorted_vals[f]


@dataclass
class PerfReport:
    """性能评估汇总报告."""

    concurrency_levels: dict[int, dict[str, Any]] = field(default_factory=dict)
    raw_samples: list[PerfSample] = field(default_factory=list)


async def measure_single_query(
    client: httpx.AsyncClient,
    base_url: str,
    item: EvalItemV2,
    token: str = "",
) -> PerfSample:
    """单次 SSE 请求的精细计时 — 捕获 TTFT 与总响应时间."""
    sample = PerfSample(item_id=item.id)
    t_start = time.perf_counter()
    first_token_recorded = False

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with client.stream(
            "POST",
            f"{base_url}/api/v1/qa/ask",
            json={
                "question": item.question,
                "session_id": f"perf_{item.id}_{int(t_start*1000)}",
                "scene": item.scene,
            },
            headers=headers,
            timeout=httpx.Timeout(120.0),
        ) as resp:
            if resp.status_code != 200:
                sample.status = "error"
                sample.error = f"HTTP {resp.status_code}"
                sample.total_ms = (time.perf_counter() - t_start) * 1000
                return sample

            async for line in resp.aiter_lines():
                t_now = time.perf_counter()

                if not first_token_recorded and line.startswith("event: message"):
                    sample.ttft_ms = (t_now - t_start) * 1000
                    first_token_recorded = True

                if line.startswith("event: message"):
                    sample.token_count += 1

                if line.startswith("event: done"):
                    sample.total_ms = (t_now - t_start) * 1000

                if line.startswith("event: error"):
                    try:
                        data_parts = line.split("data:", 1)
                        if len(data_parts) > 1:
                            err_data = json.loads(data_parts[1].strip())
                    except (json.JSONDecodeError, IndexError):
                        err_data = {}
                    sample.status = "error"
                    sample.error = str(err_data.get("message", "unknown"))[:100]
                    sample.total_ms = (t_now - t_start) * 1000

    except httpx.TimeoutException:
        sample.status = "timeout"
        sample.error = "timeout"
        sample.total_ms = (time.perf_counter() - t_start) * 1000
    except httpx.ConnectError as e:
        sample.status = "error"
        sample.error = f"connect: {e}"
    except Exception as e:
        sample.status = "error"
        sample.error = str(e)[:200]

    return sample


async def benchmark_concurrency(
    base_url: str,
    items: list[EvalItemV2],
    concurrency_levels: list[int],
    token: str = "",
) -> PerfReport:
    """多并发等级压测，生成 QPS vs 延迟曲线."""
    report = PerfReport()

    for concurrency in concurrency_levels:
        cycle = (items * (concurrency // len(items) + 1))[:concurrency]

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_connections=concurrency + 10),
        ) as client:
            t0 = time.perf_counter()
            tasks = [
                measure_single_query(client, base_url, item, token)
                for item in cycle
            ]
            samples = await asyncio.gather(*tasks)
            elapsed = time.perf_counter() - t0

        success = [s for s in samples if s.status == "success"]
        ttft_values = [s.ttft_ms for s in success if s.ttft_ms > 0]
        total_values = [s.total_ms for s in success if s.total_ms > 0]
        token_counts = [s.token_count for s in success]

        level_stats = {
            "concurrency": concurrency,
            "total_requests": len(samples),
            "success": len(success),
            "errors": len(samples) - len(success),
            "qps": round(len(samples) / elapsed, 2) if elapsed > 0 else 0,
            "elapsed_seconds": round(elapsed, 2),
            "success_rate": round(len(success) / len(samples), 4) if samples else 0,
        }

        if ttft_values:
            level_stats.update({
                "ttft_p50_ms": round(percentile(ttft_values, 50), 0),
                "ttft_p95_ms": round(percentile(ttft_values, 95), 0),
                "ttft_p99_ms": round(percentile(ttft_values, 99), 0),
                "ttft_avg_ms": round(sum(ttft_values) / len(ttft_values), 0),
                "ttft_min_ms": round(min(ttft_values), 0),
                "ttft_max_ms": round(max(ttft_values), 0),
            })

        if total_values:
            level_stats.update({
                "total_p50_ms": round(percentile(total_values, 50), 0),
                "total_p95_ms": round(percentile(total_values, 95), 0),
                "total_p99_ms": round(percentile(total_values, 99), 0),
                "total_avg_ms": round(sum(total_values) / len(total_values), 0),
            })

        if token_counts:
            level_stats["avg_output_tokens"] = round(sum(token_counts) / len(token_counts), 1)

        report.concurrency_levels[concurrency] = level_stats
        report.raw_samples.extend(samples)

    return report
