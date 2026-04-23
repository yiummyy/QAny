from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QASettings(Base):
    __tablename__ = "qa_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.user_id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="qa_settings_single_row"),)
