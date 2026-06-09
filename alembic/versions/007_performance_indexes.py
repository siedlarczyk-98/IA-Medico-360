"""performance indexes on hot query columns

Revision ID: 007_performance_indexes
Revises: 006_otp_failed_attempts
Create Date: 2026-06-09
"""

from alembic import op

revision = "007_performance_indexes"
down_revision = "006_otp_failed_attempts"
branch_labels = None
depends_on = None


# (index_name, table, columns_sql)
INDEXES = [
    # users.email já possui índice único (constraint UNIQUE) — não duplicar.
    ("ix_conversations_user_status_updatedat", "conversations", "(user_id, status, updatedat DESC)"),
    ("ix_interactions_user_feature", "interactions", "(user_id, feature)"),
    ("ix_interactions_conversation_feature", "interactions", "(conversation_id, feature)"),
    ("ix_interactions_conversation_user_status", "interactions", "(conversation_id, user_id, status)"),
    ("ix_interactions_user_createdat", "interactions", "(user_id, createdat DESC)"),
    ("ix_interaction_responses_interaction", "interaction_responses", "(interaction_id)"),
    ("ix_pharma_alerts_interaction", "pharma_alerts", "(interaction_id)"),
    ("ix_interaction_medications_interaction", "interaction_medications", "(interaction_id)"),
    ("ix_pubmed_validations_interaction", "pubmed_validations", "(interaction_id)"),
    ("ix_semantic_cache_expires_at", "semantic_cache", "(expires_at)"),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}")


def downgrade() -> None:
    for name, _table, _cols in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
