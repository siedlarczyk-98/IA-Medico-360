"""Tabelas da LP de parceiros (schema landing_pages).

Mesmo desenho de accounting/finance: resposta tipada 1:1 (partner_answers)
mais selecao 1:N (partner_category_selections) penduradas em submissions.

Revision ID: 000h_lp_partners
Revises: 000g_lp_notify_flag
Create Date: 2026-08-26 00:00:00.000000
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '000h_lp_partners'
down_revision: str | None = '000g_lp_notify_flag'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.create_table(
        'partner_answers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('career_stage', sa.String(length=100), nullable=False),
        sa.Column('desired_brands', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], [f'{SCHEMA}.submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('submission_id'),
        schema=SCHEMA,
    )
    op.create_table(
        'partner_category_selections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('option', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], [f'{SCHEMA}.submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA,
    )

    landing_pages_table = sa.table(
        'landing_pages',
        sa.column('id', sa.UUID()),
        sa.column('slug', sa.String()),
        sa.column('name', sa.String()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.bulk_insert(
        landing_pages_table,
        [{'id': uuid.uuid4(), 'slug': 'partners', 'name': 'Parceiros', 'created_at': datetime.now(UTC)}],
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.landing_pages WHERE slug = 'partners'")
    op.drop_table('partner_category_selections', schema=SCHEMA)
    op.drop_table('partner_answers', schema=SCHEMA)
