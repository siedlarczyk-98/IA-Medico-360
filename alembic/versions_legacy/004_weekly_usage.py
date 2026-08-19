"""add user_weekly_usage table

Revision ID: 004_weekly_usage
Revises: 003_drop_phone_check
Create Date: 2026-06-08
"""

import sqlalchemy as sa

from alembic import op

revision = "004_weekly_usage"
down_revision = "003_drop_phone_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_weekly_usage",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_weekly_usage")
