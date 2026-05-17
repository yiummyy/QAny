"""add documents.tags column

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=True),
    )
    op.create_index(
        "idx_documents_tags",
        "documents",
        ["tags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_documents_tags", table_name="documents")
    op.drop_column("documents", "tags")
