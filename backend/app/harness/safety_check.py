"""Answer content safety audit — sensitive keyword + compliance + hallucination URL detection (B5)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable keyword lists (MVP hardcoded, future: load from JSON config)
# ---------------------------------------------------------------------------

SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    # (regex pattern, category)
    (r"走私|贩毒|洗钱|赌博", "违法"),
    (r"炸药|制毒|枪支制造", "危险品"),
    (r"自杀.*方法|割腕.*步骤", "自残"),
]

# Internal system URLs / phone numbers / emails that the LLM might hallucinate
HALLUCINATION_PATTERNS: list[tuple[str, str]] = [
    # (regex pattern, description)
    (r"https?://(?!docs\.internal\.com|kb\.company\.com|wiki\.internal\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "疑似幻觉外部URL"),
    (r"联系电话[：:]\s*\d{3,4}-?\d{7,8}", "疑似幻觉电话号码"),
    (r"[a-zA-Z0-9._%+-]+@(?!company\.com|internal\.com)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "疑似幻觉外部邮箱"),
]

KNOWN_INTERNAL_DOMAINS = {
    "docs.internal.com", "kb.company.com", "wiki.internal.com",
}


# ---------------------------------------------------------------------------
# Safety decision model
# ---------------------------------------------------------------------------


@dataclass
class SafetyDecision:
    """Result of content safety audit."""

    verdict: str  # "pass" | "warn" | "block"
    flags: list[dict] = field(default_factory=list)
    # Each flag: {"category": str, "match": str, "severity": "high"|"medium"}

    def is_blocked(self) -> bool:
        return self.verdict == "block"


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------


async def audit_answer(
    answer: str,
    sources: list[dict] | None = None,
    user_permission_level: str = "L1",
) -> SafetyDecision:
    """Run content safety audit on the generated answer.

    Called AFTER streaming completes — does not block first-token latency.
    """
    flags: list[dict] = []

    # 1. Sensitive keyword check
    for pattern, category in SENSITIVE_PATTERNS:
        for match in re.finditer(pattern, answer, re.IGNORECASE):
            flags.append({
                "category": category,
                "match": match.group()[:50],
                "severity": "high",
            })

    # 2. Hallucination URL / phone / email check
    for pattern, desc in HALLUCINATION_PATTERNS:
        for match in re.finditer(pattern, answer, re.IGNORECASE):
            matched_text = match.group()
            # Allow known internal domains
            if desc == "疑似幻觉外部URL":
                if any(d in matched_text for d in KNOWN_INTERNAL_DOMAINS):
                    continue
            if desc == "疑似幻觉外部邮箱":
                if matched_text.endswith("@company.com") or matched_text.endswith("@internal.com"):
                    continue
            flags.append({
                "category": desc,
                "match": matched_text[:80],
                "severity": "medium",
            })

    # 3. Permission compliance: check if answer references high-permission content
    if sources:
        for src in sources:
            src_pl = src.get("permission_level", "L1")
            if _pl_exceeds(src_pl, user_permission_level):
                flags.append({
                    "category": "越权引用",
                    "match": f"引用了 {src_pl} 级别文档 '{src.get('doc_name', '?')}'，用户仅有 {user_permission_level}",
                    "severity": "high",
                })

    # Determine verdict
    high_severity = [f for f in flags if f["severity"] == "high"]
    medium_severity = [f for f in flags if f["severity"] == "medium"]

    if high_severity:
        logger.warning("safety: block — %d high-severity flags", len(high_severity))
        return SafetyDecision(verdict="block", flags=flags)
    elif medium_severity:
        logger.info("safety: warn — %d medium-severity flags", len(medium_severity))
        return SafetyDecision(verdict="warn", flags=flags)

    return SafetyDecision(verdict="pass", flags=flags)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pl_exceeds(content_pl: str, user_pl: str) -> bool:
    """Check if content permission level exceeds user's access."""
    order = {"L1": 1, "L2": 2, "L3": 3}
    return order.get(content_pl, 0) > order.get(user_pl, 0)


# Fallback answer returned when content is blocked
SAFETY_FALLBACK = "抱歉，系统检测到回答内容存在安全风险，已自动拦截。如需帮助请联系管理员。"
