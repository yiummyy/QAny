from sqlalchemy import Column, String

from app.models.base import Base, TimestampMixin


def test_base_is_declarative():
    assert hasattr(Base, "metadata")
    assert Base.metadata is not None


def test_timestamp_mixin_exposes_columns():
    class Dummy(Base, TimestampMixin):
        __tablename__ = "dummy"
        id = Column(String, primary_key=True)

    cols = {c.name for c in Dummy.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" in cols
