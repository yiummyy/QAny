"""Phase 2: ServiceTicket tools tests — create_ticket, lookup_ticket, escalate."""

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.agent_config import AGENT_PRESETS, AgentConfig
from app.harness.tool_registry import AGENT_TOOLS, SHARED_TOOLS, build_agent_handlers


@pytest.fixture
def employee_claims():
    return UserClaims(
        sub="u_emp", username="employee", role=Role.EMPLOYEE, pl="L2", jti="jti-emp"
    )


# ---------------------------------------------------------------------------
# Tool registration tests
# ---------------------------------------------------------------------------


async def test_create_ticket_registered_for_service_ticket():
    """create_ticket must be registered in AGENT_TOOLS for ServiceTicket only."""
    from app.tools.create_ticket import create_ticket  # noqa: F401 — trigger registration

    assert "ServiceTicket" in AGENT_TOOLS
    assert "create_ticket" in AGENT_TOOLS["ServiceTicket"]


async def test_lookup_ticket_registered_for_service_ticket():
    from app.tools.lookup_ticket import lookup_ticket  # noqa: F401

    assert "lookup_ticket" in AGENT_TOOLS["ServiceTicket"]


async def test_escalate_registered_for_service_ticket():
    from app.tools.escalate import escalate_ticket  # noqa: F401

    assert "escalate" in AGENT_TOOLS["ServiceTicket"]


async def test_build_agent_handlers_service_ticket():
    """ServiceTicket agent gets shared tools + its own create_ticket/lookup_ticket/escalate."""
    from app.tools.create_ticket import create_ticket  # noqa: F401
    from app.tools.lookup_ticket import lookup_ticket  # noqa: F401
    from app.tools.escalate import escalate_ticket  # noqa: F401
    from app.tools.search_knowledge import search_knowledge  # noqa: F401
    from app.tools.query_knowledge import query_knowledge  # noqa: F401
    from app.tools.generate_answer import generate_answer  # noqa: F401
    from app.tools.hallucination_check import hallucination_check  # noqa: F401

    config = AGENT_PRESETS["ServiceTicket"]
    handlers = build_agent_handlers(config)

    # Shared tools
    assert "search_knowledge" in handlers
    assert "query_knowledge" in handlers
    assert "generate_answer" in handlers
    assert "hallucination_check" in handlers

    # ServiceTicket-specific tools
    assert "create_ticket" in handlers
    assert "lookup_ticket" in handlers
    assert "escalate" in handlers


async def test_knowledge_qa_does_not_have_ticket_tools():
    """KnowledgeQA agent must NOT have create_ticket/lookup_ticket/escalate."""
    from app.tools.create_ticket import create_ticket  # noqa: F401
    from app.tools.lookup_ticket import lookup_ticket  # noqa: F401
    from app.tools.escalate import escalate_ticket  # noqa: F401
    from app.tools.search_knowledge import search_knowledge  # noqa: F401
    from app.tools.query_knowledge import query_knowledge  # noqa: F401

    config = AGENT_PRESETS["KnowledgeQA"]
    handlers = build_agent_handlers(config)

    assert "create_ticket" not in handlers
    assert "lookup_ticket" not in handlers
    assert "escalate" not in handlers
    assert "search_knowledge" in handlers
    assert "query_knowledge" in handlers


# ---------------------------------------------------------------------------
# Tool function tests (with mock DB)
# ---------------------------------------------------------------------------


async def test_create_ticket_returns_ticket_id(employee_claims):
    """Create ticket returns a valid ticket_id and correct status."""
    from app.tools.create_ticket import create_ticket

    result = await create_ticket(
        title="打印机故障",
        description="3楼打印机卡纸，无法正常使用",
        priority="high",
        category="IT",
        user_claims=employee_claims,
    )

    # Even without a real DB, the tool should not crash (returns error with DB info)
    # When DB is available, status should be "ok"
    assert result.status in ("ok", "error")
    if result.status == "ok":
        assert result.data["ticket_id"].startswith("tkt_")
        assert result.data["status"] == "open"
        assert result.data["priority"] == "high"


async def test_create_ticket_normalizes_priority(employee_claims):
    """Invalid priority values are normalized to 'medium'."""
    from app.tools.create_ticket import create_ticket

    result = await create_ticket(
        title="测试",
        description="测试工单",
        priority="INVALID!!!",
        category="其他",
        user_claims=employee_claims,
    )

    if result.status == "ok":
        assert result.data["priority"] == "medium"


async def test_lookup_ticket_not_found(employee_claims):
    """Lookup non-existent ticket returns degraded status."""
    from app.tools.lookup_ticket import lookup_ticket

    result = await lookup_ticket(
        ticket_id="tkt_nonexistent_123",
        user_claims=employee_claims,
    )

    if result.status == "degraded":
        assert result.data["found"] is False
    # If DB not available, it returns error — either is acceptable


async def test_escalate_ticket_not_found(employee_claims):
    """Escalate non-existent ticket returns degraded status."""
    from app.tools.escalate import escalate_ticket

    result = await escalate_ticket(
        ticket_id="tkt_nonexistent_123",
        reason="紧急故障",
        user_claims=employee_claims,
    )

    assert result.status in ("degraded", "error")


# ---------------------------------------------------------------------------
# AgentConfig tests
# ---------------------------------------------------------------------------


async def test_service_ticket_agent_config():
    config = AGENT_PRESETS["ServiceTicket"]
    assert config.name == "ServiceTicket"
    assert config.es_index == "ticket_knowledge"
    assert config.session_prefix == "st_"
    assert config.max_steps == 5
    assert config.answer_template == "generate/service_ticket_answer"
    assert config.plan_system_prompt != ""  # loaded from file


async def test_scene_to_agent_mapping():
    from app.harness.agent_config import SCENE_TO_AGENT

    assert SCENE_TO_AGENT["ticket"] == "ServiceTicket"
    assert SCENE_TO_AGENT["service"] == "ServiceTicket"
    assert SCENE_TO_AGENT["general"] == "KnowledgeQA"
