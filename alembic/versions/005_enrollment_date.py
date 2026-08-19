"""add enrollment_date to users

Revision ID: 005_enrollment_date
Revises: 004_weekly_usage
Create Date: 2026-06-08
"""

import sqlalchemy as sa

from alembic import op

revision = "005_enrollment_date"
down_revision = "004_weekly_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("enrollment_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "enrollment_date")
