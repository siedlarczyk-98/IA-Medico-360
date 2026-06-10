"""add folders table and folder_id to conversations

Revision ID: 010_folders
Revises: 009_extra_metadata
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "010_folders"
down_revision = "009_extra_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("createdat", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updatedat", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_folders_user_createdat", "folders", ["user_id", "createdat"])

    op.add_column(
        "conversations",
        sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("folders.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "folder_id")
    op.drop_index("ix_folders_user_createdat", table_name="folders")
    op.drop_table("folders")
