"""Tool: search_crm — query CRM for customer profile (SalesContent agent only, B9)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool


class SearchCRMInput(BaseModel):
    customer_name: str = Field(..., description="客户名称或公司名")
    opportunity_stage: str = Field(
        default="",
        description="销售阶段筛选: 初步接触/需求确认/方案演示/报价/谈判/已签约",
    )


@register_agent_tool("SalesContent", "search_crm", SearchCRMInput, timeout=10.0, max_retries=1)
async def search_crm(
    customer_name: str,
    opportunity_stage: str = "",
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Query CRM for customer profile and recent interactions (MVP: mock)."""
    # MVP mock — returns placeholder customer data
    profile = {
        "customer_name": customer_name,
        "company": f"{customer_name}科技有限公司",
        "industry": "制造业",
        "pipeline_stage": opportunity_stage or "需求确认",
        "recent_interactions": [
            {"date": "2026-04-25", "type": "电话沟通", "summary": "客户对产品X感兴趣"},
            {"date": "2026-04-20", "type": "邮件", "summary": "发送了产品方案"},
        ],
        "key_contacts": [
            {"name": "张总", "role": "采购总监", "phone": "138****1234"},
        ],
        "annual_revenue": "5000万-1亿",
    }

    return ToolResult(
        status="ok",
        summary=f"CRM查询: {customer_name} ({profile['pipeline_stage']})",
        data={"customer_profile": profile},
    )
