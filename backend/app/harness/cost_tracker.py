"""Cost tracker — model-specific pricing + preflight estimation (B7)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Model pricing per 1K tokens (RMB)
MODEL_PRICES: dict[str, dict[str, float]] = {
    "qwen-plus": {"input": 0.002, "output": 0.006},
    "qwen-turbo": {"input": 0.0008, "output": 0.002},
    "qwen-max": {"input": 0.02, "output": 0.06},
    "deepseek-chat": {"input": 0.001, "output": 0.002},
    "deepseek-reasoner": {"input": 0.004, "output": 0.016},
    # Embedding / rerank (Local deployment, cost is 0, keeping keys for compatibility)
    "bge-m3": {"per_1k_tokens": 0.0},
    "bge-reranker-v2-m3": {"per_chunk": 0.0},
}


@dataclass
class CostTracker:
    """Tracks per-stage token usage and computes cost with model-specific pricing."""

    model: str = "qwen-plus"
    stages: dict[str, dict[str, int]] = field(default_factory=dict)
    # stages[stage] = {"input_tokens": N, "output_tokens": M}

    def record(self, stage: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        entry = self.stages.setdefault(stage, {"input_tokens": 0, "output_tokens": 0})
        entry["input_tokens"] += input_tokens
        entry["output_tokens"] += output_tokens

    def total_cost_rmb(self) -> float:
        prices = MODEL_PRICES.get(self.model, MODEL_PRICES["qwen-plus"])
        total = 0.0
        for entry in self.stages.values():
            total += (entry["input_tokens"] / 1000) * prices.get("input", 0)
            total += (entry["output_tokens"] / 1000) * prices.get("output", 0)
        return round(total, 6)

    def total_input_tokens(self) -> int:
        return sum(e["input_tokens"] for e in self.stages.values())

    def total_output_tokens(self) -> int:
        return sum(e["output_tokens"] for e in self.stages.values())

    def summary(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.total_input_tokens(),
            "output_tokens": self.total_output_tokens(),
            "cost_rmb": self.total_cost_rmb(),
            "stages": dict(self.stages),
        }


def estimate_cost(
    query_length: int,
    model: str = "qwen-plus",
    expected_steps: int = 3,
) -> dict:
    """Preflight cost estimate before running the agent.

    Returns estimated min/max cost in RMB.
    """
    prices = MODEL_PRICES.get(model, MODEL_PRICES["qwen-plus"])
    input_price = prices.get("input", 0.002)
    output_price = prices.get("output", 0.006)

    # Rough heuristic: each step ≈ plan (500 in + 100 out) + tool (variable)
    plan_tokens_per_step = 500
    tool_tokens_per_step = query_length * 2  # rough: query + chunks
    output_tokens_per_step = 300

    steps_min = 2  # simple question: plan→search→generate→final = 2 plan calls
    steps_max = expected_steps

    def _cost(steps: int) -> float:
        total_in = steps * (plan_tokens_per_step + tool_tokens_per_step)
        total_out = steps * output_tokens_per_step
        return round((total_in / 1000) * input_price + (total_out / 1000) * output_price, 6)

    return {
        "model": model,
        "estimated_min_rmb": _cost(steps_min),
        "estimated_max_rmb": _cost(steps_max),
    }
