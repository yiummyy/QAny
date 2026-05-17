"""Degrade State tests — fine-grained circuit breaker with half-open state."""

import time
from unittest.mock import patch

import pytest

from app.harness.degrade import TOOL_TO_POOL, CircuitPool, DegradeState
from app.harness.models import ToolResult


# ---------------------------------------------------------------------------
# CircuitPool unit tests (no async needed)
# ---------------------------------------------------------------------------


class TestCircuitPool:
    def test_initial_state_is_closed(self):
        pool = CircuitPool(name="test", max_failures=3)
        assert pool.state == "closed"
        assert pool.failure_count == 0
        assert pool.allow() is True

    def test_closed_to_open_after_max_failures(self):
        pool = CircuitPool(name="test", max_failures=3)
        for _ in range(3):
            pool.record_failure()
        assert pool.state == "open"
        assert pool.allow() is False

    def test_closed_stays_closed_below_max_failures(self):
        pool = CircuitPool(name="test", max_failures=3)
        for _ in range(2):
            pool.record_failure()
        assert pool.state == "closed"
        assert pool.allow() is True

    def test_open_transitions_to_half_open_after_recovery_timeout(self):
        pool = CircuitPool(name="test", max_failures=2, recovery_timeout=0.01)
        for _ in range(2):
            pool.record_failure()
        assert pool.state == "open"
        time.sleep(0.02)  # wait past recovery timeout
        assert pool.allow() is True
        assert pool.state == "half_open"

    def test_half_open_probe_success_recovery(self):
        pool = CircuitPool(name="test", max_failures=2, recovery_timeout=0.01)
        for _ in range(2):
            pool.record_failure()
        time.sleep(0.02)
        pool.allow()  # transition to half_open
        pool.record_success()
        assert pool.state == "closed"
        assert pool.failure_count == 0

    def test_half_open_probe_failure_reopen(self):
        pool = CircuitPool(name="test", max_failures=2, recovery_timeout=0.01)
        for _ in range(2):
            pool.record_failure()
        time.sleep(0.02)
        pool.allow()  # transition to half_open
        pool.record_failure()
        assert pool.state == "open"

    def test_record_success_resets_counter_in_closed(self):
        pool = CircuitPool(name="test", max_failures=3)
        pool.record_failure()
        pool.record_failure()
        pool.record_success()
        assert pool.failure_count == 0
        assert pool.state == "closed"


# ---------------------------------------------------------------------------
# DegradeState tests (async)
# ---------------------------------------------------------------------------


class TestDegradeStatePools:
    async def test_check_returns_none_when_healthy(self):
        ds = DegradeState()
        result = await ds.check("hybrid_search")
        assert result is None

    async def test_plan_pool_independent_from_answer_pool(self):
        """Plan pool tripped does NOT affect answer pool."""
        ds = DegradeState()
        for _ in range(3):
            ds.record_failure("plan")
        # plan should be blocked
        plan_result = await ds.check("plan")
        assert plan_result is not None
        assert plan_result.status == "degraded"
        # answer_generation should still be healthy
        answer_result = await ds.check("answer_generation")
        assert answer_result is None

    async def test_answer_pool_blocks_when_tripped(self):
        ds = DegradeState()
        for _ in range(3):
            ds.record_failure("answer_generation")
        result = await ds.check("answer_generation")
        assert result is not None
        assert result.status == "degraded"

    async def test_intent_recognition_pool_blocks_at_2_failures(self):
        ds = DegradeState()
        ds.record_failure("intent_recognition")
        assert await ds.check("intent_recognition") is None  # 1 failure OK
        ds.record_failure("intent_recognition")
        result = await ds.check("intent_recognition")  # 2nd → open
        assert result is not None
        assert result.status == "degraded"

    async def test_hallucination_pool_blocks_at_2_failures(self):
        ds = DegradeState()
        for _ in range(2):
            ds.record_failure("hallucination")
        result = await ds.check("hallucination")
        assert result is not None

    async def test_record_success_resets_pool(self):
        ds = DegradeState()
        for _ in range(3):
            ds.record_failure("plan")
        assert await ds.check("plan") is not None  # blocked
        ds.record_success("plan")
        assert await ds.check("plan") is None  # recovered

    async def test_unknown_pool_returns_none(self):
        ds = DegradeState()
        result = await ds.check("nonexistent_pool")
        assert result is None

    async def test_legacy_tool_name_mapping(self):
        """Old tool names like 'generate_answer' map to correct pool."""
        ds = DegradeState()
        assert "generate_answer" in TOOL_TO_POOL
        for _ in range(3):
            ds.record_failure("answer_generation")
        # Old tool name should be blocked
        result = await ds.check("generate_answer")
        assert result is not None
        assert result.status == "degraded"

    async def test_record_failure_with_legacy_tool_name(self):
        """record_failure with old tool name maps correctly."""
        ds = DegradeState()
        for _ in range(3):
            ds.record_failure("generate_answer")
        result = await ds.check("answer_generation")
        assert result is not None

    async def test_record_success_with_legacy_tool_name(self):
        """record_success with old tool name maps correctly."""
        ds = DegradeState()
        for _ in range(3):
            ds.record_failure("answer_generation")
        ds.record_success("generate_answer")
        assert await ds.check("answer_generation") is None

    async def test_any_sentinel_allows_when_some_pools_healthy(self):
        """_any_ should not block if at least one pool is healthy."""
        ds = DegradeState()
        for _ in range(3):
            ds.record_failure("plan")
        # plan is blocked but other pools are fine
        result = await ds.check("_any_")
        assert result is None

    async def test_any_sentinel_blocks_when_all_pools_open(self):
        """_any_ should block only when ALL pools are open."""
        ds = DegradeState()
        for pool_name in ds.pools:
            for _ in range(ds.pools[pool_name].max_failures):
                ds.record_failure(pool_name)
        result = await ds.check("_any_")
        assert result is not None
        assert result.status == "degraded"


# ---------------------------------------------------------------------------
# Backward-compatible legacy tests (adapted)
# ---------------------------------------------------------------------------


class TestDegradeStateLegacyCompat:
    async def test_check_blocks_llm_on_too_many_failures(self):
        """Legacy: record_llm_failure still trips all LLM pools."""
        ds = DegradeState()
        for _ in range(3):
            ds.record_llm_failure()
        result = await ds.check("generate_answer")
        assert result is not None
        assert result.status == "degraded"

    async def test_check_blocks_rewrite_query_on_llm_failures(self):
        ds = DegradeState()
        for _ in range(3):
            ds.record_llm_failure()
        result = await ds.check("rewrite_query")
        assert result is not None

    async def test_check_blocks_hallucination_check_on_llm_failures(self):
        ds = DegradeState()
        for _ in range(3):
            ds.record_llm_failure()
        result = await ds.check("hallucination_check")
        assert result is not None

    async def test_check_allows_hybrid_search_despite_llm_failures(self):
        ds = DegradeState()
        for _ in range(3):
            ds.record_llm_failure()
        result = await ds.check("hybrid_search")
        assert result is None  # hybrid_search doesn't use LLM

    async def test_llm_success_resets_all_pools(self):
        ds = DegradeState()
        for _ in range(2):
            ds.record_llm_failure()
        ds.record_llm_success()
        for pool_name in ds.pools:
            assert ds.pools[pool_name].failure_count == 0
            assert ds.pools[pool_name].state == "closed"


# ---------------------------------------------------------------------------
# ES / embedder health (unchanged behavior)
# ---------------------------------------------------------------------------


class TestDegradeStateESEmbedder:
    async def test_check_returns_error_when_es_unhealthy(self):
        ds = DegradeState()
        ds.mark_es_unhealthy()
        result = await ds.check("hybrid_search")
        assert result is not None
        assert result.status == "error"
        assert "ES" in result.summary

    async def test_check_returns_degraded_when_embedder_unhealthy(self):
        ds = DegradeState()
        ds.mark_embedder_unhealthy()
        result = await ds.check("hybrid_search")
        assert result is not None
        assert result.status == "degraded"
        assert "Embedder" in result.summary

    async def test_es_health_can_be_restored(self):
        ds = DegradeState()
        ds.mark_es_unhealthy()
        ds.mark_es_healthy()
        result = await ds.check("hybrid_search")
        assert result is None

    async def test_embedder_health_can_be_restored(self):
        ds = DegradeState()
        ds.mark_embedder_unhealthy()
        ds.mark_embedder_healthy()
        result = await ds.check("hybrid_search")
        assert result is None

    async def test_es_embedder_health_independent_from_llm_pools(self):
        """ES/embedder health checks are independent of LLM circuit pools."""
        ds = DegradeState()
        ds.mark_es_unhealthy()
        # trip all LLM pools too
        for _ in range(3):
            ds.record_llm_failure()
        # ES check still works independently
        result = await ds.check("hybrid_search")
        assert result is not None
        assert result.status == "error"
        # But answer pool is also blocked
        result2 = await ds.check("answer_generation")
        assert result2 is not None
        assert result2.status == "degraded"


# ---------------------------------------------------------------------------
# Cost limit (unchanged)
# ---------------------------------------------------------------------------


class TestCostLimit:
    async def test_check_cost_limit_returns_none_when_under_limit(self):
        ds = DegradeState()
        result = await ds.check_cost_limit(50.0, 100.0)
        assert result is None

    async def test_check_cost_limit_returns_degraded_when_over_limit(self):
        ds = DegradeState()
        result = await ds.check_cost_limit(100.0, 100.0)
        assert result is not None
        assert result.status == "degraded"

    async def test_check_cost_limit_returns_none_when_limit_zero(self):
        ds = DegradeState()
        result = await ds.check_cost_limit(1000.0, 0.0)
        assert result is None
