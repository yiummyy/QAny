from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(8), nullable=False)
    department: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.user_id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_documents_status", "status"),
        Index("idx_documents_file_hash", "file_hash", unique=True),
    )
