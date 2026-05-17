"""documents table — add knowledge_base column

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("knowledge_base", sa.String(32), nullable=False, server_default="qa"),
    )
    op.create_index("idx_documents_kb", "documents", ["knowledge_base"])


def downgrade() -> None:
    op.drop_index("idx_documents_kb", table_name="documents")
    op.drop_column("documents", "knowledge_base")
