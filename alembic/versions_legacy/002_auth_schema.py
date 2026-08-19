"""auth schema: nullable user fields, med_status, onboarding, otp_codes, invite_tokens

Revision ID: 002_auth_schema
Revises: 001_add_semantic_cache
Create Date: 2026-06-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "002_auth_schema"
down_revision = "001_add_semantic_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make user fields nullable for staged onboarding
    op.alter_column("users", "name", nullable=True)
    op.alter_column("users", "crm", nullable=True)
    op.alter_column("users", "crm_state", nullable=True)

    # New user fields
    op.add_column("users", sa.Column("med_status", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default="false"))

    # OTP codes table
    op.create_table(
        "otp_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("code", sa.String(6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("otp_codes_email_idx", "otp_codes", ["email"])

    # Invite tokens table
    op.create_table(
        "invite_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("token", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("invite_tokens")
    op.drop_index("otp_codes_email_idx", table_name="otp_codes")
    op.drop_table("otp_codes")
    op.drop_column("users", "onboarding_complete")
    op.drop_column("users", "med_status")
    op.alter_column("users", "crm_state", nullable=False)
    op.alter_column("users", "crm", nullable=False)
    op.alter_column("users", "name", nullable=False)
