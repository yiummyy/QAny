from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


def test_base_is_declarative() -> None:
    assert hasattr(Base, "metadata")
    assert Base.metadata is not None


def test_timestamp_mixin_exposes_columns() -> None:
    class Dummy(Base, TimestampMixin):
        __tablename__ = "dummy_ts"
        id: Mapped[str] = mapped_column(String, primary_key=True)

    cols = {c.name for c in Dummy.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" in cols
