"""JWT sign/decode — HS256, access + refresh per Spec §5.1.

- access_token: 15min, carries full claims (sub/username/role/pl/dept)
- refresh_token: 7d, carries only sub + jti (no role info, reduces blast radius)
- jti: 32-char urlsafe token, used as Redis blacklist key

The module depends on app.config.get_settings() for JWT_SECRET & TTLs, and
is framework-agnostic (no FastAPI imports) so it can be unit-tested without
an HTTP stack.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from jose import jwt

from app.config import get_settings

_ALGORITHM = "HS256"


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def _new_jti() -> str:
    return secrets.token_urlsafe(16)


def _secret() -> str:
    return get_settings().jwt_secret.get_secret_value()


def create_access_token(
    *,
    user_id: str,
    username: str,
    role: str,
    permission_level: str,
    department: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return (access_token, jti)."""
    settings = get_settings()
    iat = now or datetime.now(timezone.utc)
    exp = iat + timedelta(seconds=settings.jwt_access_ttl_seconds)
    jti = _new_jti()
    payload: dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "role": role,
        "pl": permission_level,
        "dept": department,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "token_type": TokenType.ACCESS.value,
    }
    token = jwt.encode(payload, _secret(), algorithm=_ALGORITHM)
    return token, jti


def create_refresh_token(
    *,
    user_id: str,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Return (refresh_token, jti). Refresh carries only sub+jti."""
    settings = get_settings()
    iat = now or datetime.now(timezone.utc)
    exp = iat + timedelta(seconds=settings.jwt_refresh_ttl_seconds)
    jti = _new_jti()
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": int(iat.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "token_type": TokenType.REFRESH.value,
    }
    token = jwt.encode(payload, _secret(), algorithm=_ALGORITHM)
    return token, jti


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """Decode + verify signature/exp, enforce token_type match.

    Raises jose.JWTError on any failure — caller maps it to 40101 at the
    FastAPI boundary.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        _secret(),
        algorithms=[_ALGORITHM],
        options={"require": ["exp", "iat", "sub", "jti", "token_type"]},
    )
    if payload.get("token_type") != expected_type.value:
        from jose import JWTError
        raise JWTError(f"token_type mismatch: expected {expected_type.value}")
    return payload
