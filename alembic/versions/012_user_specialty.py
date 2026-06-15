"""add specialty column to users

Revision ID: 012_user_specialty
Revises: 011_missing_indexes
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from alembic import op

revision = "012_user_specialty"
down_revision = "011_missing_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("specialty", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "specialty")
