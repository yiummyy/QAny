"""Tool: Redundant permission check — belt-and-suspenders guard."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.auth.claims import UserClaims
from app.harness.models import ToolResult
from app.harness.tool_registry import register
from app.rbac.filter_builder import ROLE_LEVEL_MATRIX


class PermissionCheckInput(BaseModel):
    chunks: list[dict[str, Any]]


@register("permission_check", PermissionCheckInput)
async def permission_check(
    chunks: list[dict[str, Any]],
    *,
    user_claims: UserClaims,
) -> ToolResult:
    """Verify every chunk's permission_level is within the user's allowed levels."""
    allowed = ROLE_LEVEL_MATRIX.get(user_claims.role.value, ["L1"])
    violations = []

    for i, chunk in enumerate(chunks):
        chunk_pl = chunk.get("permission_level", "L1")
        if chunk_pl not in allowed:
            violations.append({"index": i, "chunk_pl": chunk_pl, "user_pl": allowed})

    if violations:
        filtered = [c for i, c in enumerate(chunks) if i not in {v["index"] for v in violations}]
        return ToolResult(
            status="degraded",
            summary=f"过滤 {len(violations)} 条越权结果",
            data={"chunks": filtered, "violations": violations},
        )

    return ToolResult(status="ok", summary="权限校验通过", data={"chunks": chunks})
