"""add missing performance indexes for otp_codes and audit_logs

Revision ID: 011_missing_indexes
Revises: 010_folders
Create Date: 2026-06-10
"""

from alembic import op

revision = "011_missing_indexes"
down_revision = "010_folders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_otp_codes_expires_at", "otp_codes", ["expires_at"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_createdat", "audit_logs", ["createdat"])
    op.create_index("ix_audit_logs_interaction_id", "audit_logs", ["interaction_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_interaction_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_createdat", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_otp_codes_expires_at", table_name="otp_codes")
