"""Intent gate: short-circuit non-knowledge queries before expensive RAG steps.

Placed after rewrite_query and before hybrid_search in search_knowledge.
Uses pure rule-based pattern matching — zero LLM cost for chitchat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    blocked: bool
    """True = short-circuit RAG pipeline, return pre-built response."""
    status: str
    """Always ``"chitchat"`` when blocked."""
    category: str
    """One of: ``"greeting"`` | ``"thanks"`` | ``"farewell"`` | ``"identity"`` | ``"capability"`` | ``"out_of_scope"``."""
    response: str
    """Pre-built response text to yield directly."""


# ---------------------------------------------------------------------------
# Static response templates
# ---------------------------------------------------------------------------

GREETING_RESPONSE = (
    "你好！我是企业知识库问答助手，可以帮你查询公司制度、流程指引、"
    "产品知识、故障排查方案和培训资料。请问有什么可以帮你的？"
)

THANKS_RESPONSE = "不客气！如有其他问题随时问我。"

FAREWELL_RESPONSE = "再见！如有需要随时回来。"

IDENTITY_RESPONSE = (
    "我是企业知识库问答助手，专注于公司制度、流程指引、"
    "产品知识、故障排查和培训资料咨询。请问有什么可以帮你的？"
)

CAPABILITY_GUIDE = (
    "我目前的知识库中未包含这方面的内容。以下是你可以向我咨询的方面：\n\n"
    "- **公司制度查询**：年假、加班、报销、社保、薪酬等\n"
    "- **流程指引**：入职、离职、转正、调岗、请假审批等\n"
    "- **产品知识**：产品报价、方案对比、客户案例等\n"
    "- **故障排查**：设备报错、网络故障、账号权限等\n"
    "- **培训学习**：操作手册、SOP 流程、考试资料等\n\n"
    "如需查询其他内容，请联系管理员补充相关知识库。"
)

# ---------------------------------------------------------------------------
# Pattern → (category, response) mapping
# Order matters: first match wins.
# ---------------------------------------------------------------------------

_CHITCHAT_PATTERNS: list[tuple[str, str, str]] = [
    (r"^(你好|您好|hi|hello|嗨|早上好|下午好|晚上好|哈[喽啰]|在吗|在不在)", "greeting", GREETING_RESPONSE),
    (r"^(谢谢|感谢|多谢|thanks|thank)", "thanks", THANKS_RESPONSE),
    (r"^(再见|拜拜|bye|回头见|下次见|晚安|明天见)", "farewell", FAREWELL_RESPONSE),
    (r"^(你是谁|你叫什么|你的名字|who are you)", "identity", IDENTITY_RESPONSE),
    (r"^(你会什么|你能做什么|你能干什么|你有什么功能|你怎么用)", "capability", CAPABILITY_GUIDE),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check(
    query: str,
    intent: str,
    entities: list[str],
    tags: list[str],
    *,
    rewrite_failed: bool = False,
    rewritten_query: str | None = None,
    confidence: float | None = None,
) -> GateResult | None:
    """Check whether *query* should be short-circuited.

    Returns ``GateResult`` if the query should skip RAG entirely,
    or ``None`` to continue with normal search → rerank → generate.
    """
    if rewrite_failed:
        return None

    # Only gate when intent is "其他" with no extracted entities and no predicted tags.
    # Having entities or tags means the LLM found *some* signal worth searching for.
    if entities:
        return None
    if tags:
        return None
    if intent != "其他":
        return None

    # LLM did coreference resolution or rewriting — signal found, let it through
    if rewritten_query and rewritten_query.strip() != query.strip():
        return None

    # Low confidence + intent=其他 → LLM is unsure, let search try
    if confidence is not None and confidence < 0.5:
        return None

    query_stripped = query.strip().lower()

    for pattern, category, response in _CHITCHAT_PATTERNS:
        if re.match(pattern, query_stripped):
            return GateResult(blocked=True, status="chitchat", category=category, response=response)

    # Falls through all patterns → out of scope, return capability guide
    return GateResult(
        blocked=True,
        status="chitchat",
        category="out_of_scope",
        response=CAPABILITY_GUIDE,
    )
