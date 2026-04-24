"""Typed representation of JWT claims — single source of truth for downstream."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    ADMIN = "admin"
    EMPLOYEE = "employee"
    GUEST = "guest"


PermissionLevel = Literal["L1", "L2", "L3"]


class UserClaims(BaseModel):
    """Parsed JWT access-token payload (Spec §5.1)."""

    model_config = ConfigDict(frozen=True)

    sub: str = Field(..., description="user_id")
    username: str
    role: Role
    pl: PermissionLevel
    dept: str | None = None
    jti: str

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @classmethod
    def from_jwt_payload(cls, payload: dict[str, Any]) -> "UserClaims":
        """Only call with *access-token* payloads.

        Refresh tokens do NOT contain `username/role/pl/dept` (Spec §5.1
        blast-radius containment) — passing a refresh payload here will
        raise KeyError on `payload["username"]`.
        """
        return cls(
            sub=payload["sub"],
            username=payload["username"],
            role=payload["role"],
            pl=payload["pl"],
            dept=payload.get("dept"),
            jti=payload["jti"],
        )
