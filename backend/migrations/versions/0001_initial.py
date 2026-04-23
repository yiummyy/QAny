"""initial schema — 5 tables + qa_settings default row

Revision ID: 0001
Revises:
Create Date: 2026-04-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("permission_level", sa.String(8), nullable=False),
        sa.Column("department", sa.String(64)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_users_role", "users", ["role"])

    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_url", sa.Text),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("permission_level", sa.String(8), nullable=False),
        sa.Column("department", sa.String(64)),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("uploaded_by", sa.String(32), sa.ForeignKey("users.user_id")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_file_hash", "documents", ["file_hash"], unique=True)

    op.create_table(
        "qa_logs",
        sa.Column("log_id", sa.String(32), primary_key=True),
        sa.Column("session_id", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("scene", sa.String(16), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text),
        sa.Column("intent", sa.String(32)),
        sa.Column("entities", postgresql.JSONB),
        sa.Column("sources", postgresql.JSONB),
        sa.Column("tools_called", postgresql.JSONB),
        sa.Column("confidence", sa.String(8)),
        sa.Column("confidence_score", sa.Numeric(4, 3)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("model_name", sa.String(32)),
        sa.Column("cost_rmb", sa.Numeric(10, 4)),
        sa.Column("response_time_ms", sa.Integer),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.Integer),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_qa_logs_user_created", "qa_logs", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_qa_logs_session", "qa_logs", ["session_id"])
    op.create_index("idx_qa_logs_created", "qa_logs", [sa.text("created_at DESC")])

    op.create_table(
        "feedbacks",
        sa.Column("feedback_id", sa.String(32), primary_key=True),
        sa.Column("log_id", sa.String(32), sa.ForeignKey("qa_logs.log_id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("feedback_type", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32)),
        sa.Column("comment", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_feedbacks_log", "feedbacks", ["log_id"])

    op.create_table(
        "qa_settings",
        sa.Column("id", sa.Integer, primary_key=True, server_default="1"),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("updated_by", sa.String(32), sa.ForeignKey("users.user_id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="qa_settings_single_row"),
    )
    op.execute("""
        INSERT INTO qa_settings (id, config) VALUES (1, '{
          "rerank_enabled": true,
          "hallucination_threshold": 0.6,
          "max_context_docs": 5,
          "model_routing": {"answer_generation": "qwen-plus", "intent_recognition": "qwen-turbo"},
          "cost_daily_limit_rmb": 1000
        }'::jsonb)
    """)


def downgrade() -> None:
    op.drop_table("qa_settings")
    op.drop_index("idx_feedbacks_log", table_name="feedbacks")
    op.drop_table("feedbacks")
    op.drop_index("idx_qa_logs_created", table_name="qa_logs")
    op.drop_index("idx_qa_logs_session", table_name="qa_logs")
    op.drop_index("idx_qa_logs_user_created", table_name="qa_logs")
    op.drop_table("qa_logs")
    op.drop_index("idx_documents_file_hash", table_name="documents")
    op.drop_index("idx_documents_status", table_name="documents")
    op.drop_table("documents")
    op.drop_index("idx_users_role", table_name="users")
    op.drop_table("users")
