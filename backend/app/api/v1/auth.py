"""/api/v1/auth/* — Spec §4.2 auth group."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.blacklist import is_revoked, pop_pair, register_pair, revoke
from app.auth.claims import UserClaims
from app.auth.jwt import TokenType, create_access_token, create_refresh_token, decode_token
from app.auth.login_limiter import LoginBlocked, ensure_not_blocked, record_failure, reset
from app.auth.passwords import verify_password
from app.auth.user_repo import get_by_username, touch_last_login
from app.config import get_settings
from app.storage.pg import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=True)


# ------------ Pydantic schemas ---------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    user_id: str
    username: str
    role: str
    permission_level: str
    department: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    user: UserOut


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"


# ------------ Helpers -------------------------------------------------------


def _unauthorized(code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _rate_limited(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"code": 42900, "message": "请求过于频繁，请稍后重试"},
        headers={"Retry-After": str(retry_after)},
    )


# ------------ Endpoints -----------------------------------------------------


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> LoginResponse:
    try:
        await ensure_not_blocked(body.username)
    except LoginBlocked as blocked:
        raise _rate_limited(blocked.retry_after) from blocked

    user = await get_by_username(session, body.username)

    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        await record_failure(body.username)
        raise _unauthorized(40101, "用户名或密码错误")

    access_token, access_jti = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        permission_level=user.permission_level,
        department=user.department,
    )
    refresh_token, refresh_jti = create_refresh_token(user_id=user.user_id)
    await register_pair(
        access_jti=access_jti,
        refresh_jti=refresh_jti,
        ttl_seconds=get_settings().jwt_refresh_ttl_seconds,
    )

    await reset(body.username)
    await touch_last_login(session, user_id=user.user_id)
    await session.commit()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserOut(
            user_id=user.user_id,
            username=user.username,
            role=user.role,
            permission_level=user.permission_level,
            department=user.department,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    from sqlalchemy import select

    from app.models.user import User

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.REFRESH)
    except JWTError:
        raise _unauthorized(40101, "Refresh token 失效") from None

    if await is_revoked(payload["jti"]):
        raise _unauthorized(40101, "Token 已登出")

    user = (
        await session.execute(select(User).where(User.user_id == payload["sub"]))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise _unauthorized(40102, "账户禁用")

    new_access, _ = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        permission_level=user.permission_level,
        department=user.department,
    )
    return RefreshResponse(access_token=new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Response:
    for token_type in (TokenType.ACCESS, TokenType.REFRESH):
        try:
            payload = decode_token(credentials.credentials, expected_type=token_type)
            break
        except JWTError:
            continue
    else:
        raise _unauthorized(40101, "Token 失效")

    exp = int(payload["exp"])
    now = int(datetime.now(UTC).timestamp())
    jti = payload["jti"]

    await revoke(jti=jti, ttl_seconds=exp - now)

    partner_jti = await pop_pair(jti)
    if partner_jti is not None:
        await revoke(
            jti=partner_jti,
            ttl_seconds=get_settings().jwt_refresh_ttl_seconds,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
async def me(claims: UserClaims = Depends(get_current_user)) -> UserOut:
    return UserOut(
        user_id=claims.sub,
        username=claims.username,
        role=claims.role.value,
        permission_level=claims.pl,
        department=claims.dept,
    )
