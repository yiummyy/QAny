"""Tool: create_ticket — create a new service ticket (ServiceTicket agent only)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool
from app.storage.pg import get_sessionmaker


class CreateTicketInput(BaseModel):
    title: str = Field(..., description="工单标题（简洁描述问题）")
    description: str = Field(..., description="问题详细描述")
    priority: str = Field(
        default="medium",
        description="优先级: low / medium / high / urgent",
    )
    category: str = Field(
        default="其他",
        description="问题分类: IT / HR / 行政 / 财务 / 其他",
    )


@register_agent_tool("ServiceTicket", "create_ticket", CreateTicketInput,
                     timeout=30.0, max_retries=2,
                     requires_confirmation=True, confirmation_timeout=120.0)
async def create_ticket(
    title: str,
    description: str,
    priority: str = "medium",
    category: str = "其他",
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Create a new service ticket. Call when knowledge base cannot answer the user."""
    ticket_id = f"tkt_{uuid.uuid4().hex[:12]}"

    # Normalize priority and category
    priority = priority.lower() if priority else "medium"
    if priority not in ("low", "medium", "high", "urgent"):
        priority = "medium"

    try:
        from app.models.service_ticket import ServiceTicket

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            ticket = ServiceTicket(
                ticket_id=ticket_id,
                title=title,
                description=description,
                priority=priority,
                category=category,
                status="open",
                created_by=user_claims.sub,
            )
            session.add(ticket)
            await session.commit()

        return ToolResult(
            status="ok",
            summary=f"工单已创建: {ticket_id} (优先级={priority}, 分类={category})",
            data={
                "ticket_id": ticket_id,
                "title": title,
                "priority": priority,
                "category": category,
                "status": "open",
            },
        )
    except Exception as exc:
        return ToolResult(
            status="error",
            summary=f"创建工单失败: {exc}",
            data={"ticket_id": None},
        )
