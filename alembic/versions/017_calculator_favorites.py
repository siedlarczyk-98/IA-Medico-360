"""Create calculator_favorites table for server-side favorite calculators

Revision ID: 017_calculator_favorites
Revises: 016_risco_cv_relax_required
Create Date: 2026-07-01
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "017_calculator_favorites"
down_revision = "016_risco_cv_relax_required"
branch_labels = None
depends_on = None

SCHEMA = "calculators"


def upgrade() -> None:
    op.create_table(
        "calculator_favorites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("public.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "calculator_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.calculator_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("createdat", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "calculator_id", name="uq_calculator_favorites_user_calculator"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculator_favorites_user",
        "calculator_favorites",
        ["user_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("calculator_favorites", schema=SCHEMA)
