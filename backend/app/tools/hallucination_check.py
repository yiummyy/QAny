"""Tool: Hallucination detection — sentence-level source verification via LLM."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_shared
from app.prompts.renderer import render
from app.providers.router import ProviderRouter

HALLUCINATION_HIGH = 0.8
HALLUCINATION_MEDIUM = 0.6
FALLBACK_ANSWER = "抱歉，我无法确定答案，建议您咨询相关部门或查阅原始文档。"


class HallucinationCheckInput(BaseModel):
    answer: str
    chunks: list[dict[str, Any]]


@register_shared("hallucination_check", HallucinationCheckInput, timeout=30.0, max_retries=0)
async def hallucination_check(
    answer: str,
    chunks: list[dict[str, Any]],
    *,
    user_claims: UserClaims,
    provider_router: ProviderRouter | None = None,
    citation_report: Any = None,
) -> ToolResult:
    """Verify answer against source chunks, sentence by sentence.

    If citation_report is provided, its programmatic findings are injected
    into the verification prompt to focus the LLM on suspicious claims.
    """
    chunks_text = _format_chunks(chunks)

    # Build citation context if a programmatic report is available
    citation_context = ""
    if citation_report and hasattr(citation_report, 'unverified'):
        unverified_count = len(getattr(citation_report, 'unverified', []))
        orphan_count = len(getattr(citation_report, 'orphan_claims', []))
        if unverified_count > 0 or orphan_count > 0:
            parts = ["## 程序化引用验证发现"]
            if unverified_count > 0:
                unverified_entries = getattr(citation_report, 'unverified', [])
                parts.append(f"- {unverified_count} 个引用存疑或漂移：")
                for uv in unverified_entries[:5]:
                    parts.append(f"  - [{uv.anchor}] {uv.sentence[:100]} (相似度: {uv.similarity})")
            if orphan_count > 0:
                orphan_entries = getattr(citation_report, 'orphan_claims', [])
                parts.append(f"- {orphan_count} 个句子声称了事实但未标注来源：")
                for oc in orphan_entries[:5]:
                    parts.append(f"  - [{oc.claim_type}] {oc.sentence[:100]}")
            parts.append("\n请重点关注以上存疑引用和无来源声称的准确性。")
            citation_context = "\n".join(parts)

    prompt = render(
        "hallucination_check",
        chunks=chunks_text,
        answer=answer,
        citation_context=citation_context,
    )

    if not answer or answer == FALLBACK_ANSWER:
        return ToolResult(
            status="ok",
            summary="兜底答案无需校验",
            data={"score": 1.0, "verdict": "high", "analysis": [], "needs_fallback": False},
        )

    if not provider_router:
        # MVP: return placeholder if no router is provided
        return ToolResult(
            status="ok",
            summary="无LLM路由，跳过幻觉检测",
            data={
                "prompt": prompt,
                "answer": answer,
                "chunks": chunks,
                "score": 1.0,
                "verdict": "high",
                "analysis": [],
                "needs_fallback": False,
            },
        )

    try:
        messages = [{"role": "user", "content": prompt}]
        result_text = await provider_router.chat(messages, stage="hallucination_check")
        parsed = parse_hallucination_result(result_text)
        return ToolResult(
            status="ok",
            summary=f"幻觉检测完成，得分: {parsed['score']}",
            data={
                "prompt": prompt,
                "answer": answer,
                "chunks": chunks,
                **parsed,
            },
        )
    except Exception as exc:
        return ToolResult(
            status="degraded",
            summary=f"幻觉检测失败: {exc}",
            data={
                "prompt": prompt,
                "answer": answer,
                "chunks": chunks,
                "score": 1.0,
                "verdict": "high",
                "analysis": [],
                "needs_fallback": False,
            },
        )


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, c in enumerate(chunks):
        content = c.get("content", "")
        doc_name = c.get("doc_name", "未知文档")
        parts.append(f"[S{i + 1}] ({doc_name}) {content}")
    return "\n\n".join(parts) if parts else "无参考文档"


def parse_hallucination_result(llm_response: str) -> dict[str, Any]:
    """Parse LLM hallucination check output to structured result."""
    text = llm_response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
    parsed = json.loads(text)
    score = float(parsed.get("score", 0))
    verdict = parsed.get("verdict", "low")
    if score >= HALLUCINATION_HIGH:
        verdict = "high"
    elif score >= HALLUCINATION_MEDIUM:
        verdict = "medium"
    else:
        verdict = "low"

    return {
        "score": score,
        "verdict": verdict,
        "analysis": parsed.get("analysis", []),
        "needs_fallback": score < HALLUCINATION_MEDIUM,
    }
