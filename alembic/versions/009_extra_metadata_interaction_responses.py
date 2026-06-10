"""add extra_metadata column to interaction_responses

Revision ID: 009_extra_metadata_interaction_responses
Revises: 008_performance_indexes_2
Create Date: 2026-06-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "009_extra_metadata"
down_revision = "008_performance_indexes_2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interaction_responses",
        sa.Column("extra_metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interaction_responses", "extra_metadata")
