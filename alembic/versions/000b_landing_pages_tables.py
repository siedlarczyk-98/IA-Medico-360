"""Tabelas de captacao das landing pages (schema landing_pages).

Catalogo (landing_pages) -> submissao comum (submissions) -> resposta
tipada por LP (accounting_answers, finance_answers) ou selecao 1:N
(benefit_selections, calculator_selections) para as LPs de campo unico.

Revision ID: 000b_lp_tables
Revises: 000a_lp_schema
Create Date: 2026-08-25 00:00:00.000000
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '000b_lp_tables'
down_revision: str | None = '000a_lp_schema'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.create_table(
        'landing_pages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
        schema=SCHEMA,
    )
    op.create_table(
        'submissions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('landing_page_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('lgpd_consent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['landing_page_id'], [f'{SCHEMA}.landing_pages.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA,
    )
    op.create_table(
        'accounting_answers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('career_stage', sa.String(length=100), nullable=False),
        sa.Column('income_method', sa.String(length=100), nullable=False),
        sa.Column('accountant_status', sa.String(length=100), nullable=False),
        sa.Column('revenue_range', sa.String(length=100), nullable=False),
        sa.Column('main_pain_point', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], [f'{SCHEMA}.submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('submission_id'),
        schema=SCHEMA,
    )
    op.create_table(
        'finance_answers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('career_stage', sa.String(length=100), nullable=False),
        sa.Column('main_pain_point', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], [f'{SCHEMA}.submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('submission_id'),
        schema=SCHEMA,
    )
    op.create_table(
        'benefit_selections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('option', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], [f'{SCHEMA}.submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA,
    )
    op.create_table(
        'calculator_selections',
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
    now = datetime.now(UTC)
    op.bulk_insert(
        landing_pages_table,
        [
            {'id': uuid.uuid4(), 'slug': 'accounting', 'name': 'Contabilidade', 'created_at': now},
            {'id': uuid.uuid4(), 'slug': 'finance', 'name': 'Finanças', 'created_at': now},
            {'id': uuid.uuid4(), 'slug': 'benefits', 'name': 'Benefícios', 'created_at': now},
            {'id': uuid.uuid4(), 'slug': 'calculators', 'name': 'Calculadoras', 'created_at': now},
        ],
    )


def downgrade() -> None:
    op.drop_table('calculator_selections', schema=SCHEMA)
    op.drop_table('benefit_selections', schema=SCHEMA)
    op.drop_table('finance_answers', schema=SCHEMA)
    op.drop_table('accounting_answers', schema=SCHEMA)
    op.drop_table('submissions', schema=SCHEMA)
    op.drop_table('landing_pages', schema=SCHEMA)
