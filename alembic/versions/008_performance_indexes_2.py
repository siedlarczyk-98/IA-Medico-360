"""additional performance indexes: composite, FK, and partial

Revision ID: 008_performance_indexes_2
Revises: 007_performance_indexes
Create Date: 2026-06-10
"""

from alembic import op

revision = "008_performance_indexes_2"
down_revision = "007_performance_indexes"
branch_labels = None
depends_on = None


# Composite index to support history filter by model
INDEXES = [
    ("ix_interaction_responses_interaction_model", "interaction_responses", "(interaction_id, model_used)"),
    ("ix_interactions_company_id", "interactions", "(company_id)"),
    ("ix_users_company_id", "users", "(company_id)"),
]

# Partial indexes — only index active rows (status = TRUE)
PARTIAL_INDEXES = [
    ("ix_interactions_active_user_createdat", "interactions", "(user_id, createdat DESC) WHERE status = TRUE"),
    ("ix_conversations_active_user_updatedat", "conversations", "(user_id, updatedat DESC) WHERE status = TRUE"),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}")
    for name, table, cols in PARTIAL_INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}")


def downgrade() -> None:
    for name, _table, _cols in INDEXES + PARTIAL_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
