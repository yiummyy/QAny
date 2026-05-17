"""Tool: escalate — escalate a service ticket (ServiceTicket agent override).

Registered as AGENT tool for ServiceTicket. OpsSupport will register its own
version with a different schema (alert escalation). The build_agent_handlers
function picks the correct one based on the active agent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register_agent_tool
from app.storage.pg import get_sessionmaker


class EscalateTicketInput(BaseModel):
    ticket_id: str = Field(..., description="要升级的工单编号")
    reason: str = Field(..., description="升级原因")


@register_agent_tool("ServiceTicket", "escalate", EscalateTicketInput,
                     timeout=15.0, max_retries=1,
                     requires_confirmation=True, confirmation_timeout=120.0)
async def escalate_ticket(
    ticket_id: str,
    reason: str,
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Escalate a service ticket's priority to urgent."""
    try:
        from app.models.service_ticket import ServiceTicket

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            ticket = await session.get(ServiceTicket, ticket_id)
            if ticket is None:
                return ToolResult(
                    status="degraded",
                    summary=f"工单 {ticket_id} 不存在，无法升级",
                    data={"ticket_id": ticket_id, "escalated": False},
                )

            ticket.priority = "urgent"
            ticket.escalated = True
            ticket.escalation_reason = reason
            await session.commit()

            return ToolResult(
                status="ok",
                summary=f"工单 {ticket_id} 已升级为 urgent（原因: {reason}）",
                data={
                    "ticket_id": ticket.ticket_id,
                    "priority": ticket.priority,
                    "escalated": True,
                    "reason": reason,
                },
            )
    except Exception as exc:
        return ToolResult(
            status="error",
            summary=f"升级工单失败: {exc}",
        )
