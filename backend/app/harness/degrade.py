"""Degradation decision center — fine-grained circuit breaker with half-open state."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.harness.models import ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-pool circuit breaker
# ---------------------------------------------------------------------------


@dataclass
class CircuitPool:
    """State machine for a single failure domain.

    States:
      closed ──连续失败≥max──▶ open ──recovery_timeout──▶ half_open
                                                             │
                                                ┌─成功─▶ closed (reset)
                                                └─失败─▶ open (reset timer)
    """

    name: str
    max_failures: int
    recovery_timeout: float = 30.0
    failure_count: int = 0
    state: str = "closed"
    last_failure_time: float = 0.0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state == "half_open":
            # Probe failed — reopen immediately
            self.state = "open"
            logger.warning("CircuitPool %s: half_open probe failed → open", self.name)
        elif self.failure_count >= self.max_failures and self.state == "closed":
            self.state = "open"
            logger.warning(
                "CircuitPool %s: %d failures reached → open (recovery in %.0fs)",
                self.name, self.failure_count, self.recovery_timeout,
            )

    def record_success(self) -> None:
        if self.state == "half_open":
            logger.info("CircuitPool %s: half_open probe succeeded → closed", self.name)
        self.failure_count = 0
        self.state = "closed"

    def allow(self) -> bool:
        """Return True if the call should proceed."""
        if self.state == "closed":
            return True
        if self.state == "open":
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = "half_open"
                logger.info("CircuitPool %s: recovery timeout → half_open (probing)", self.name)
                return True
            return False
        # half_open — allow the probe
        return True


# ---------------------------------------------------------------------------
# Tool name → pool name mapping (backward compatibility)
# ---------------------------------------------------------------------------

TOOL_TO_POOL: dict[str, str] = {
    "generate_answer": "answer_generation",
    "rewrite_query": "intent_recognition",
    "hallucination_check": "hallucination",
    "hybrid_search": "search",  # handled separately via ES/embedder health
}


# ---------------------------------------------------------------------------
# DegradeState — pool-aware circuit breaker
# ---------------------------------------------------------------------------


class DegradeState:
    """Pool-aware circuit breaker. Check before each tool call."""

    def __init__(self) -> None:
        self.pools: dict[str, CircuitPool] = {
            "plan": CircuitPool(name="plan", max_failures=3, recovery_timeout=30),
            "answer_generation": CircuitPool(name="answer_generation", max_failures=3, recovery_timeout=60),
            "intent_recognition": CircuitPool(name="intent_recognition", max_failures=2, recovery_timeout=30),
            "hallucination": CircuitPool(name="hallucination", max_failures=2, recovery_timeout=60),
        }
        self.es_healthy: bool = True
        self.embedder_healthy: bool = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, pool_name: str) -> ToolResult | None:
        """Return None to proceed, or a degraded ToolResult if circuit is open.

        Accepts both pool names (e.g. ``"answer_generation"``) and legacy
        tool names (e.g. ``"generate_answer"``) via ``TOOL_TO_POOL`` mapping.
        """
        # Resolve pool name from legacy tool name if needed
        resolved = TOOL_TO_POOL.get(pool_name, pool_name)

        # ES / embedder health (backward compat — checked via tool name)
        if pool_name in ("hybrid_search",) and not self.es_healthy:
            return ToolResult(status="error", summary="ES 不可达", data={"chunks": []})
        if pool_name in ("hybrid_search",) and not self.embedder_healthy:
            return ToolResult(
                status="degraded",
                summary="Embedder 不可用，降级为纯 BM25",
                data={"embedder_down": True},
            )

        # _any_ sentinel: check if ALL pools are open → full degradation
        if pool_name == "_any_":
            if self.pools and all(not p.allow() for p in self.pools.values()):
                return ToolResult(
                    status="degraded",
                    summary="所有 LLM 服务已熔断",
                    data={"fallback": True},
                )
            return None

        # Per-pool check
        pool = self.pools.get(resolved)
        if pool is None:
            return None  # unknown pool → always allow

        if not pool.allow():
            return ToolResult(
                status="degraded",
                summary=f"服务 {resolved} 已熔断，请稍后重试",
                data={"fallback": True, "pool": resolved},
            )
        return None

    async def check_cost_limit(
        self, today_cost_rmb: float, daily_limit_rmb: float,
    ) -> ToolResult | None:
        """Return a degraded ToolResult if the daily cost limit has been reached."""
        if daily_limit_rmb <= 0:
            return None
        if today_cost_rmb >= daily_limit_rmb:
            return ToolResult(
                status="degraded",
                summary=f"当日成本已超阈值 (¥{today_cost_rmb:.2f}/¥{daily_limit_rmb:.2f})",
                data={"code": 50900, "fallback": True, "limit": daily_limit_rmb},
            )
        return None

    def record_failure(self, pool_name: str) -> None:
        """Record a failure against a pool by name."""
        resolved = TOOL_TO_POOL.get(pool_name, pool_name)
        pool = self.pools.get(resolved)
        if pool is not None:
            pool.record_failure()

    def record_success(self, pool_name: str) -> None:
        """Record a success (resets the pool to closed)."""
        resolved = TOOL_TO_POOL.get(pool_name, pool_name)
        pool = self.pools.get(resolved)
        if pool is not None:
            pool.record_success()

    # Backward-compatible aliases
    def record_llm_failure(self) -> None:
        """Legacy: record failure against all LLM pools."""
        for name in ("plan", "answer_generation", "intent_recognition", "hallucination"):
            self.pools[name].record_failure()

    def record_llm_success(self) -> None:
        """Legacy: reset all LLM pools."""
        for name in ("plan", "answer_generation", "intent_recognition", "hallucination"):
            self.pools[name].record_success()

    # ES / embedder health (unchanged)
    def mark_es_unhealthy(self) -> None:
        self.es_healthy = False

    def mark_es_healthy(self) -> None:
        self.es_healthy = True

    def mark_embedder_unhealthy(self) -> None:
        self.embedder_healthy = False

    def mark_embedder_healthy(self) -> None:
        self.embedder_healthy = True


# ---------------------------------------------------------------------------
# Daily cost helpers (unchanged)
# ---------------------------------------------------------------------------


async def get_today_cost_rmb() -> float:
    """Read today's running cost from Redis counter ``cost:daily:{yyyy-mm-dd}``."""
    try:
        from app.storage.redis_client import get_redis

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"cost:daily:{today}"
        redis = get_redis()
        val = await redis.get(key)
        return float(val) if val else 0.0
    except Exception:
        return 0.0


async def incr_today_cost_rmb(amount: float) -> None:
    """Increment today's cost counter in Redis (best-effort, non-blocking)."""
    if amount <= 0:
        return
    try:
        from app.storage.redis_client import get_redis

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"cost:daily:{today}"
        redis = get_redis()
        await redis.incrbyfloat(key, amount)
        await redis.expire(key, 86400 * 2)
    except Exception:
        pass
