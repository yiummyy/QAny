"""Task 7d: permission_check tool tests."""

import pytest

from app.auth.claims import Role, UserClaims
from app.harness.tool_registry import TOOL_HANDLERS


@pytest.fixture
def guest_claims():
    return UserClaims(sub="g1", username="guest", role=Role.GUEST, pl="L1", jti="jti-g")


@pytest.fixture
def admin_claims():
    return UserClaims(sub="u1", username="admin", role=Role.ADMIN, pl="L3", jti="jti-1")


async def test_permission_check_registered():
    from app.tools.permission_check import permission_check

    assert "permission_check" in TOOL_HANDLERS


async def test_admin_passes_all_chunks(admin_claims):
    from app.tools.permission_check import permission_check

    chunks = [
        {"_id": "c1", "content": "L1 doc", "permission_level": "L1"},
        {"_id": "c2", "content": "L2 doc", "permission_level": "L2"},
        {"_id": "c3", "content": "L3 doc", "permission_level": "L3"},
    ]
    result = await permission_check(chunks=chunks, user_claims=admin_claims)
    assert result.status == "ok"
    assert len(result.data["chunks"]) == 3


async def test_guest_blocked_from_l2_l3(guest_claims):
    """Guest (L1 only) should have L2/L3 chunks filtered out."""
    from app.tools.permission_check import permission_check

    chunks = [
        {"_id": "c1", "content": "L1 doc", "permission_level": "L1"},
        {"_id": "c2", "content": "L2 doc", "permission_level": "L2"},
        {"_id": "c3", "content": "L3 doc", "permission_level": "L3"},
    ]
    result = await permission_check(chunks=chunks, user_claims=guest_claims)
    assert result.status == "degraded"
    assert len(result.data["chunks"]) == 1
    assert result.data["chunks"][0]["permission_level"] == "L1"


async def test_employee_passes_l1_l2():
    employee = UserClaims(sub="e1", username="emp", role=Role.EMPLOYEE, pl="L2", jti="jti-e")
    from app.tools.permission_check import permission_check

    chunks = [
        {"_id": "c1", "content": "L1 doc", "permission_level": "L1"},
        {"_id": "c2", "content": "L2 doc", "permission_level": "L2"},
        {"_id": "c3", "content": "L3 doc", "permission_level": "L3"},
    ]
    result = await permission_check(chunks=chunks, user_claims=employee)
    assert result.status == "degraded"
    assert len(result.data["chunks"]) == 2
    levels = {c["permission_level"] for c in result.data["chunks"]}
    assert levels == {"L1", "L2"}


async def test_permission_check_empty_chunks(guest_claims):
    from app.tools.permission_check import permission_check

    result = await permission_check(chunks=[], user_claims=guest_claims)
    assert result.status == "ok"
    assert result.data["chunks"] == []


async def test_permission_check_reports_violations(guest_claims):
    from app.tools.permission_check import permission_check

    chunks = [
        {"_id": "c1", "content": "secret", "permission_level": "L3"},
    ]
    result = await permission_check(chunks=chunks, user_claims=guest_claims)
    assert len(result.data["violations"]) == 1
