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


def test_all_models_have_table_names() -> None:
    from app.models.document import Document
    from app.models.feedback import Feedback
    from app.models.qa_log import QALog
    from app.models.settings import QASettings
    from app.models.user import User

    assert User.__tablename__ == "users"
    assert Document.__tablename__ == "documents"
    assert QALog.__tablename__ == "qa_logs"
    assert Feedback.__tablename__ == "feedbacks"
    assert QASettings.__tablename__ == "qa_settings"


def test_user_required_columns() -> None:
    from app.models.user import User

    cols = {c.name for c in User.__table__.columns}
    for c in ["user_id", "username", "password_hash", "role", "permission_level",
              "is_active", "created_at"]:
        assert c in cols
