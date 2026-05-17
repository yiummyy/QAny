"""Tool: generate_proposal — generate marketing proposal (SalesContent agent only, B9)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool
from app.prompts.renderer import render


class GenerateProposalInput(BaseModel):
    customer_name: str = Field(..., description="客户名称")
    product_list: list[str] = Field(default_factory=list, description="推荐产品列表")
    template: str = Field(default="standard", description="提案模板: standard/detailed/brief")
    chunks: list[dict[str, Any]] = Field(default_factory=list)


@register_agent_tool("SalesContent", "generate_proposal", GenerateProposalInput, timeout=10.0, max_retries=0)
async def generate_proposal(
    customer_name: str,
    product_list: list[str] | None = None,
    template: str = "standard",
    chunks: list[dict[str, Any]] | None = None,
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Generate a marketing proposal from product knowledge + CRM data (MVP)."""
    product_list = product_list or []
    chunks = chunks or []

    chunks_text = _format_chunks(chunks)
    products_text = ", ".join(product_list) if product_list else "通用方案"

    prompt = render(
        "generate_answer",
        query=f"为客户 {customer_name} 生成营销提案，推荐产品: {products_text}",
        chunks=chunks_text,
        permission_note=f"用户角色: {user_claims.role.value}",
    )

    return ToolResult(
        status="ok",
        summary=f"为 {customer_name} 生成{template}提案 (产品: {products_text})",
        data={
            "prompt": prompt,
            "customer_name": customer_name,
            "product_list": product_list,
            "template": template,
            "chunks": chunks,
        },
    )


def _format_chunks(chunks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, c in enumerate(chunks):
        content = c.get("content", "")
        doc_name = c.get("doc_name", "未知文档")
        parts.append(f"[S{i + 1}] ({doc_name}) {content}")
    return "\n\n".join(parts) if parts else "无相关文档"
