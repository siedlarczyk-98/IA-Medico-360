"""otp_codes: add failed_attempts column for brute-force protection

Revision ID: 006_otp_failed_attempts
Revises: 005_enrollment_date
Create Date: 2026-06-08
"""

import sqlalchemy as sa

from alembic import op

revision = "006_otp_failed_attempts"
down_revision = "005_enrollment_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "otp_codes",
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("otp_codes", "failed_attempts")
