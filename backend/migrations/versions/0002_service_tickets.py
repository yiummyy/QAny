"""service_tickets table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_tickets",
        sa.Column("ticket_id", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("category", sa.String(32), nullable=False, server_default="其他"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column(
            "created_by",
            sa.String(64),
            sa.ForeignKey("users.user_id"),
            nullable=False,
        ),
        sa.Column(
            "assigned_to",
            sa.String(64),
            sa.ForeignKey("users.user_id"),
            nullable=True,
        ),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("escalated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("escalation_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_tickets_status", "service_tickets", ["status"])
    op.create_index(
        "idx_tickets_created_by", "service_tickets", ["created_by", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_tickets_created_by", table_name="service_tickets")
    op.drop_index("idx_tickets_status", table_name="service_tickets")
    op.drop_table("service_tickets")
