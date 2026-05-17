"""UserProfile — long-term user preferences (B3)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, comment="FK → users.user_id"
    )
    preferred_scene: Mapped[str] = mapped_column(
        String(32), default="general", server_default="general"
    )
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expertise_domains: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, comment='e.g. ["运维", "HR"]'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("idx_user_profiles_dept", "department"),)
