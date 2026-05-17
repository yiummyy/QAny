"""Performance tracker — staged timing + token counting for observability (B6)."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class PerfTracker:
    """Tracks per-stage elapsed time and token usage during an agent run.

    Usage::

        perf = PerfTracker()
        async with perf.track("plan"):
            decision = await provider.plan(...)
        perf.record_tokens("plan", input_tokens=1200, output_tokens=80)
    """

    stages: dict[str, float] = field(default_factory=dict)  # stage → cumulative ms
    token_input: dict[str, int] = field(default_factory=dict)  # stage → input tokens
    token_output: dict[str, int] = field(default_factory=dict)  # stage → output tokens
    decisions: list[dict] = field(default_factory=list)  # decision trace
    ttft_ms: float | None = None  # time to first token
    _timers: dict[str, float] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Stage timing
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def track(self, stage: str):
        """Async context manager that records elapsed time for *stage*."""
        t0 = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - t0) * 1000
            self.stages[stage] = self.stages.get(stage, 0) + elapsed_ms

    def track_start(self, stage: str) -> None:
        """Manually start timing a stage (for non-async-context-manager use)."""
        self._timers[stage] = time.monotonic()

    def track_end(self, stage: str) -> float:
        """End timing and return elapsed ms."""
        t0 = self._timers.pop(stage, time.monotonic())
        elapsed_ms = (time.monotonic() - t0) * 1000
        self.stages[stage] = self.stages.get(stage, 0) + elapsed_ms
        return elapsed_ms

    # ------------------------------------------------------------------
    # Token counting
    # ------------------------------------------------------------------

    def record_tokens(self, stage: str, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Accumulate token counts for a stage."""
        if input_tokens:
            self.token_input[stage] = self.token_input.get(stage, 0) + input_tokens
        if output_tokens:
            self.token_output[stage] = self.token_output.get(stage, 0) + output_tokens

    # ------------------------------------------------------------------
    # Decision trace
    # ------------------------------------------------------------------

    def record_decision(self, step: int, decision: dict, diagnostics: dict | None = None) -> None:
        """Record a PlanDecision for offline replay."""
        self.decisions.append({
            "step": step,
            "decision": decision,
            "diagnostics": diagnostics or {},
            "timestamp_ms": int(time.monotonic() * 1000),
        })

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def total_ms(self) -> float:
        return sum(self.stages.values())

    def total_tokens(self) -> int:
        return sum(self.token_input.values()) + sum(self.token_output.values())

    def summary(self) -> dict:
        """Return a dict suitable for the DONE event ``perf`` field."""
        result: dict = {
            "stages_ms": dict(self.stages),
            "tokens": {
                "input": dict(self.token_input),
                "output": dict(self.token_output),
                "total": self.total_tokens(),
            },
            "total_ms": self.total_ms(),
        }
        if self.ttft_ms is not None:
            result["ttft_ms"] = self.ttft_ms
        return result
