"""Tests for content safety audit (B5)."""

import pytest

from app.harness.safety_check import SAFETY_FALLBACK, SafetyDecision, audit_answer


class TestAuditAnswer:
    async def test_clean_answer_passes(self):
        decision = await audit_answer("年假申请需要提前3天在OA系统提交。")
        assert decision.verdict == "pass"
        assert len(decision.flags) == 0

    async def test_sensitive_keyword_triggers_block(self):
        decision = await audit_answer("走私毒品的方法包括...")
        assert decision.verdict == "block"
        assert any("违法" in f["category"] for f in decision.flags)

    async def test_hallucinated_external_url_triggers_warn(self):
        decision = await audit_answer("详情请参考 https://www.bad-site.com/page")
        assert decision.verdict == "warn"
        assert any("URL" in f["category"] for f in decision.flags)

    async def test_internal_url_passes(self):
        decision = await audit_answer("参考 https://docs.internal.com/hr/policy")
        assert decision.verdict == "pass"

    async def test_hallucinated_phone_triggers_warn(self):
        decision = await audit_answer("联系电话: 021-12345678")
        assert decision.verdict == "warn"
        assert any("电话" in f["category"] for f in decision.flags)

    async def test_permission_escalation_triggers_block(self):
        sources = [
            {"doc_name": "高管薪酬.md", "permission_level": "L3", "doc_id": "d1"},
        ]
        decision = await audit_answer("高管年薪为...", sources=sources, user_permission_level="L1")
        assert decision.verdict == "block"
        assert any("越权" in f["category"] for f in decision.flags)

    async def test_same_permission_level_passes(self):
        sources = [
            {"doc_name": "高管薪酬.md", "permission_level": "L3", "doc_id": "d1"},
        ]
        decision = await audit_answer("高管年薪为...", sources=sources, user_permission_level="L3")
        assert decision.verdict == "pass"

    async def test_multiple_flags_block_wins(self):
        """High severity flags override medium warnings."""
        decision = await audit_answer(
            "参考 https://external.com 走私方法 联系电话: 010-12345678"
        )
        assert decision.verdict == "block"


class TestSafetyDecision:
    def test_is_blocked_true(self):
        d = SafetyDecision(verdict="block", flags=[{"category": "违法", "match": "x", "severity": "high"}])
        assert d.is_blocked() is True

    def test_is_blocked_false_warn(self):
        d = SafetyDecision(verdict="warn")
        assert d.is_blocked() is False

    def test_is_blocked_false_pass(self):
        d = SafetyDecision(verdict="pass")
        assert d.is_blocked() is False


class TestSafetyFallback:
    def test_fallback_is_non_empty(self):
        assert len(SAFETY_FALLBACK) > 0
