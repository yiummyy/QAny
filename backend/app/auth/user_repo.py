"""Minimum user read path for auth flows."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    """Return the User row or None (NOT raising)."""
    stmt = select(User).where(User.username == username)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


async def touch_last_login(session: AsyncSession, *, user_id: str) -> None:
    """Bump `last_login_at` to NOW(UTC). Caller is responsible for commit."""
    stmt = (
        update(User)
        .where(User.user_id == user_id)
        .values(last_login_at=datetime.now(UTC))
    )
    await session.execute(stmt)
