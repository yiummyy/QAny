from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QALog(Base):
    __tablename__ = "qa_logs"

    log_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.user_id"), nullable=False
    )
    scene: Mapped[str] = mapped_column(String(16), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entities: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sources: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    tools_called: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(8), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_rmb: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_qa_logs_user_created", "user_id", "created_at"),
        Index("idx_qa_logs_session", "session_id"),
        Index("idx_qa_logs_created", "created_at"),
    )
