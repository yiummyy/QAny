"""Tool: lookup_ticket — query an existing ticket (ServiceTicket agent only)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool
from app.storage.pg import get_sessionmaker


class LookupTicketInput(BaseModel):
    ticket_id: str = Field(..., description="工单编号，如 tkt_xxx")


@register_agent_tool("ServiceTicket", "lookup_ticket", LookupTicketInput, timeout=15.0, max_retries=1)
async def lookup_ticket(
    ticket_id: str,
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Look up an existing service ticket by ID."""
    try:
        from app.models.service_ticket import ServiceTicket

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            ticket = await session.get(ServiceTicket, ticket_id)
            if ticket is None:
                return ToolResult(
                    status="degraded",
                    summary=f"工单 {ticket_id} 不存在",
                    data={"ticket_id": ticket_id, "found": False},
                )

            return ToolResult(
                status="ok",
                summary=f"工单 {ticket_id}: 状态={ticket.status}, 优先级={ticket.priority}",
                data={
                    "ticket_id": ticket.ticket_id,
                    "title": ticket.title,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "category": ticket.category,
                    "escalated": ticket.escalated,
                    "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                },
            )
    except Exception as exc:
        return ToolResult(
            status="error",
            summary=f"查询工单失败: {exc}",
        )
