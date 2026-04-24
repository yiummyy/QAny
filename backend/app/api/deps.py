"""FastAPI dependency wiring for auth — Spec §5.2 chain."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.blacklist import is_revoked
from app.auth.claims import Role, UserClaims
from app.auth.jwt import TokenType, decode_token
from app.auth.user_repo import get_by_username
from app.storage.pg import get_db

_bearer = HTTPBearer(auto_error=False)


def _auth_error(code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> UserClaims:
    if credentials is None or not credentials.credentials:
        raise _auth_error(40101, "缺少 Authorization Bearer token")

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except JWTError:
        raise _auth_error(40101, "Token 失效") from None

    if await is_revoked(payload["jti"]):
        raise _auth_error(40101, "Token 已登出")

    user = await get_by_username(session, payload["username"])
    if user is None or not user.is_active:
        raise _auth_error(40102, "账户禁用")

    return UserClaims.from_jwt_payload(payload)


def require_role(*allowed: str):  # type: ignore[no-untyped-def]
    """Factory dependency — allow only the listed roles."""
    allowed_set = {Role(r) for r in allowed}

    async def _dep(
        claims: UserClaims = Depends(get_current_user),
    ) -> UserClaims:
        if claims.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 40301, "message": "您暂无权限查看此内容"},
            )
        return claims

    return _dep


require_admin = require_role("admin")
require_any_user = require_role("admin", "employee", "guest")
