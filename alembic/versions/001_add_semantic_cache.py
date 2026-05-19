"""add semantic_cache table

Revision ID: 001_add_semantic_cache
Revises:
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "001_add_semantic_cache"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "semantic_cache",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mode", sa.String(50), nullable=False),
        sa.Column("normalized_prompt", sa.Text, nullable=False),
        sa.Column("prompt_embedding", sa.Text, nullable=False),  # stored as vector via raw SQL
        sa.Column("response_json", JSONB, nullable=False),
        sa.Column("hit_count", sa.Integer, default=0, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Replace text column with actual vector type
    op.execute("ALTER TABLE semantic_cache DROP COLUMN prompt_embedding")
    op.execute("ALTER TABLE semantic_cache ADD COLUMN prompt_embedding vector(1536) NOT NULL DEFAULT array_fill(0, ARRAY[1536])::vector")
    op.execute("ALTER TABLE semantic_cache ALTER COLUMN prompt_embedding DROP DEFAULT")

    op.execute(
        "CREATE INDEX semantic_cache_embedding_idx ON semantic_cache "
        "USING ivfflat (prompt_embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute("CREATE INDEX semantic_cache_mode_expires_idx ON semantic_cache (mode, expires_at)")


def downgrade() -> None:
    op.drop_table("semantic_cache")
