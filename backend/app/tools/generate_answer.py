"""Tool: LLM answer generation with mandatory citations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_shared
from app.prompts.renderer import render

FALLBACK_ANSWER = "抱歉，我无法确定答案，建议您咨询相关部门或查阅原始文档。"
MIN_SCORE_THRESHOLD = 0.45  # 提升阈值以防止低相关度碎片触发 LLM 缝合幻觉


class GenerateAnswerInput(BaseModel):
    query: str
    chunks: list[dict[str, Any]]


@register_shared("generate_answer", GenerateAnswerInput, timeout=10.0, max_retries=0)
async def generate_answer(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    user_claims: UserClaims,
    template_name: str = "generate_answer",
) -> ToolResult:
    """Generate answer from retrieved chunks with mandatory citation. Returns fallback if scores too low."""
    # Only apply the score threshold when the reranker has scored every chunk.
    # _rrf_score is a positional fusion score (~0.01-0.02), not a relevance
    # score — treating it as relevance would incorrectly degrade every response
    # when the reranker hasn't run or has degraded.
    if chunks and all("rerank_score" in c for c in chunks):
        # 如果所有 chunk 的重排分都低于 MIN_SCORE_THRESHOLD (0.45)，说明检索到的可能只是
        # 主题相关的碎片，并没有真正能回答问题的片段。直接拦截，防止 LLM 拼凑幻觉。
        if all(float(c["rerank_score"]) < MIN_SCORE_THRESHOLD for c in chunks):
            return ToolResult(
                status="degraded",
                summary=f"检索相关度不足 (最高分低于 {MIN_SCORE_THRESHOLD})，返回兜底回答",
                data={"answer": FALLBACK_ANSWER, "sources": []},
            )

    # Empty chunks → no knowledge available to base answer on
    if not chunks:
        return ToolResult(
            status="degraded",
            summary="知识库中未找到相关内容",
            data={"answer": FALLBACK_ANSWER, "sources": []},
        )

    chunks_text = _format_chunks(chunks)
    permission_note = _permission_note(user_claims)
    prompt = render(
        template_name,
        query=query,
        chunks=chunks_text,
        permission_note=permission_note,
    )

    # G4: Include top rerank score in summary for Plan LLM diagnostics
    top_score = 0.0
    if chunks:
        scores = [float(c.get("rerank_score", 0)) for c in chunks if "rerank_score" in c]
        if scores:
            top_score = max(scores)

    return ToolResult(
        status="ok",
        summary=f"基于 {len(chunks)} 个片段生成答案 (最高分{top_score:.2f})",
        data={
            "prompt": prompt,
            "query": query,
            "chunks": chunks,
            "answer": None,  # filled by agent_loop via LLM or fallback
            "sources": [],
        },
    )


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, c in enumerate(chunks):
        content = c.get("content", "")
        doc_name = c.get("doc_name", "未知文档")
        parts.append(f"[S{i + 1}] ({doc_name}) {content}")
    return "\n\n".join(parts) if parts else "无相关文档"



def _permission_note(user_claims: UserClaims) -> str:
    role_notes = {
        "admin": "你拥有全部权限，可以访问所有级别的文档。",
        "employee": "你拥有员工权限，可访问 L1/L2 级别文档。",
        "guest": "你为访客权限，仅可访问 L1 公开文档。",
    }
    return role_notes.get(user_claims.role.value, "请根据你的权限级别提供答案。")
