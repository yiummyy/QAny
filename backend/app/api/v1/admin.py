"""Minimum admin router — only /ping for Phase 2 gate demo.

Real admin endpoints (settings / logs / metrics / knowledge) will be added in
later Phases. The sole purpose of /ping is to lock the role gate via tests.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin, require_any_user
from app.auth.claims import UserClaims

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/ping")
async def admin_ping(claims: UserClaims = Depends(require_admin)) -> dict[str, object]:
    return {"pong": True, "caller": claims.username}


@router.get("/whoami")
async def whoami(claims: UserClaims = Depends(require_any_user)) -> dict[str, object]:
    """Any authenticated user (guest/employee/admin) can hit this."""
    return {"role": claims.role.value, "pl": claims.pl}
