"""Add image_base64 and image_media_type to file_extractions

Revision ID: 014_file_extraction_image_columns
Revises: 013_file_extractions
Create Date: 2026-06-19
"""
import sqlalchemy as sa

from alembic import op

revision = "014_img_columns"
down_revision = "013_file_extractions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("file_extractions", sa.Column("image_base64", sa.Text(), nullable=True))
    op.add_column("file_extractions", sa.Column("image_media_type", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("file_extractions", "image_media_type")
    op.drop_column("file_extractions", "image_base64")
