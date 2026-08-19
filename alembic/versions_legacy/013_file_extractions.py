"""create file_extractions table

Revision ID: 013_file_extractions
Revises: 012_user_specialty
Create Date: 2026-06-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "013_file_extractions"
down_revision = "012_user_specialty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("extracted_text", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_file_extractions_user_id", "file_extractions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_file_extractions_user_id", table_name="file_extractions")
    op.drop_table("file_extractions")
