"""drop phone_number check constraint

Revision ID: 003_drop_phone_check
Revises: 002_auth_schema
Create Date: 2026-06-08
"""

from alembic import op

revision = "003_drop_phone_check"
down_revision = "002_auth_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("users_phone_number_check", "users", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "users_phone_number_check",
        "users",
        r"phone_number ~ '^\+[1-9]\d{6,14}$'",
    )
