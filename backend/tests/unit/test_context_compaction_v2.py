"""Unit tests for context compaction optimization (Spec: context-compaction-optimization)."""

import re

from app.harness.context import MIN_TOKEN_DELTA, should_compact
from app.harness.models import Context
from app.harness.agent_loop import extract_constraints


# ---------------------------------------------------------------------------
# should_compact — adaptive cooldown
# ---------------------------------------------------------------------------


class FakeContextHighTokens:
    """Fake context that reports a given token count."""
    def __init__(self, tokens: int):
        self._tokens = tokens

    def token_count(self) -> int:
        return self._tokens


def test_should_compact_below_threshold():
    ctx = FakeContextHighTokens(2500)
    assert should_compact(ctx, last_compact_step=0, current_step=5) is False


def test_should_compact_mild_urgency_not_enough_steps():
    ctx = FakeContextHighTokens(3500)  # urgency ~1.17 (mild)
    # last compact at step 3, current step 3 → 0 steps since
    assert should_compact(ctx, last_compact_step=3, current_step=3) is False


def test_should_compact_mild_urgency_enough_steps():
    ctx = FakeContextHighTokens(3500)
    # last compact at step 3, current step 6 → 3 steps since (>= 2)
    assert should_compact(ctx, last_compact_step=3, current_step=6) is True


def test_should_compact_moderate_urgency():
    ctx = FakeContextHighTokens(4000)  # urgency ~1.33 (moderate)
    # cooldown = 1, steps since = 1 → should fire
    assert should_compact(ctx, last_compact_step=3, current_step=4) is True


def test_should_compact_severe_urgency():
    ctx = FakeContextHighTokens(5000)  # urgency ~1.67 (severe)
    # cooldown = 0, should fire immediately
    assert should_compact(ctx, last_compact_step=3, current_step=3) is True


def test_should_compact_critical_urgency():
    ctx = FakeContextHighTokens(7000)  # urgency ~2.33 (critical)
    assert should_compact(ctx, last_compact_step=3, current_step=3) is True


def test_should_compact_token_delta_protection():
    """Mild urgency but token count barely grew → skip compaction."""
    ctx = FakeContextHighTokens(3500)
    # last_token_count = 3400 → delta = 100 < MIN_TOKEN_DELTA(500)
    assert should_compact(
        ctx, last_compact_step=0, current_step=3, last_token_count=3400,
    ) is False


def test_should_compact_token_delta_exceeded():
    ctx = FakeContextHighTokens(4000)
    # last_token_count = 3300 → delta = 700 >= MIN_TOKEN_DELTA(500)
    assert should_compact(
        ctx, last_compact_step=0, current_step=3, last_token_count=3300,
    ) is True


# ---------------------------------------------------------------------------
# extract_constraints — rule-based constraint detection
# ---------------------------------------------------------------------------


def test_extract_scope_only_look():
    results = extract_constraints("只看华东区的数据")
    types = [r[0] for r in results]
    assert "scope" in types or "region" in types


def test_extract_time_range_recent_months():
    results = extract_constraints("近3个月的报销记录")
    types = [r[0] for r in results]
    assert "time_range" in types


def test_extract_region():
    results = extract_constraints("上海地区的销售数据")
    types = [r[0] for r in results]
    assert "region" in types


def test_extract_product_line():
    results = extract_constraints("CRM产品的更新日志")
    types = [r[0] for r in results]
    assert "product_line" in types


def test_extract_no_constraint():
    results = extract_constraints("年假怎么算？")
    assert len(results) == 0


def test_extract_multiple_constraints():
    results = extract_constraints("只看华东区近3个月CRM产品的数据")
    # Should match at least: region (华东), time_range (近3个月), product_line (CRM产品)
    types = [r[0] for r in results]
    assert "region" in types
    assert "time_range" in types


# ---------------------------------------------------------------------------
# Context.pin_constraint
# ---------------------------------------------------------------------------


def test_pin_constraint_adds_to_list():
    ctx = Context(system_prompt="test")
    ctx.pin_constraint("只看华东区", "region", source_step=1)
    assert len(ctx.pinned_constraints) == 1
    assert ctx.pinned_constraints[0].constraint == "只看华东区"
    assert ctx.pinned_constraints[0].constraint_type == "region"
    assert ctx.pinned_constraints[0].source_step == 1


def test_pin_constraint_default_expires():
    ctx = Context(system_prompt="test")
    ctx.pin_constraint("测试", "other")
    assert ctx.pinned_constraints[0].expires_after_steps == 0  # never expires


def test_pin_multiple_constraints():
    ctx = Context(system_prompt="test")
    ctx.pin_constraint("只看华东区", "region")
    ctx.pin_constraint("近3个月", "time_range")
    assert len(ctx.pinned_constraints) == 2
