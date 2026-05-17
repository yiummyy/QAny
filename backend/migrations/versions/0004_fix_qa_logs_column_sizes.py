"""fix qa_logs column sizes — align with ORM model String(64)

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-27

The initial migration created qa_logs columns as String(32) but the ORM
model was later updated to String(64).  UUID session IDs (36 chars) and
prefixed session IDs (e.g. "kqa_<uuid>", 40 chars) overflow VARCHAR(32).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("qa_logs", "log_id",
                    existing_type=sa.String(32), type_=sa.String(64))
    op.alter_column("qa_logs", "session_id",
                    existing_type=sa.String(32), type_=sa.String(64))
    op.alter_column("qa_logs", "user_id",
                    existing_type=sa.String(32), type_=sa.String(64))


def downgrade() -> None:
    op.alter_column("qa_logs", "log_id",
                    existing_type=sa.String(64), type_=sa.String(32))
    op.alter_column("qa_logs", "session_id",
                    existing_type=sa.String(64), type_=sa.String(32))
    op.alter_column("qa_logs", "user_id",
                    existing_type=sa.String(64), type_=sa.String(32))
