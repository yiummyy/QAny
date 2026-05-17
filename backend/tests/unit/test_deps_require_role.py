"""require_role 的纯逻辑单测（不走 HTTP），get_current_user 的 HTTP 走 Task 9 集成测试。"""

import pytest
from fastapi import HTTPException

from app.api.deps import require_admin, require_any_user
from app.auth.claims import Role, UserClaims


def _claims(role: str) -> UserClaims:
    return UserClaims(
        sub="u", username="u", role=role, pl="L1", jti="j",
    )


@pytest.mark.asyncio
async def test_require_admin_allows_admin():
    dep = require_admin
    result = await dep(_claims("admin"))
    assert result.role is Role.ADMIN


@pytest.mark.asyncio
async def test_require_admin_rejects_employee():
    dep = require_admin
    with pytest.raises(HTTPException) as exc_info:
        await dep(_claims("employee"))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == 40301


@pytest.mark.asyncio
async def test_require_admin_rejects_guest():
    dep = require_admin
    with pytest.raises(HTTPException) as exc_info:
        await dep(_claims("guest"))
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == 40301


@pytest.mark.asyncio
async def test_require_any_user_allows_all_three_roles():
    dep = require_any_user
    for role in ("admin", "employee", "guest"):
        result = await dep(_claims(role))
        assert result.role.value == role
