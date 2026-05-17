"""Tool: BGE-Reranker secondary ranking — Top-20 → Top-5."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register
from app.knowledge.reranker import rerank as _rerank


class RerankInput(BaseModel):
    query: str
    chunks: list[dict[str, Any]]
    top_k: int = 5


@register("rerank", RerankInput)
async def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    top_k: int = 5,
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Re-rank chunks using BGE-Reranker-v2-m3."""
    if not chunks:
        return ToolResult(status="ok", summary="无结果需重排", data={"chunks": []})

    try:
        ranked = await _rerank(query, chunks, top_k=top_k)
        return ToolResult(
            status="ok",
            summary=f"重排后保留 {len(ranked)} 条",
            data={"chunks": ranked},
        )
    except Exception as exc:
        # Degrade: pass through unranked top_k
        return ToolResult(
            status="degraded",
            summary=f"重排降级，返回原始 top_{top_k}: {exc}",
            data={"chunks": chunks[:top_k]},
        )
