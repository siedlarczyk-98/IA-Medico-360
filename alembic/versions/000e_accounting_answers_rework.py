"""Ajusta accounting_answers ao form real da LP (schema landing_pages).

O front real (Lovable) veio com 2 divergencias do escopo original:
- "Principal dor" e multi-select, nao single-select -> vira tabela filho
  (accounting_pain_selections), mesmo padrao de benefit_selections.
- Tem um campo a mais, "quanto pagaria pelo servico" -> willingness_to_pay.

Nenhuma submissao real ainda existe nessas tabelas (LP nao estava no ar),
entao o rework e seguro sem migracao de dados.

Revision ID: 000e_acct_rework
Revises: 000d_lp_email_flag
Create Date: 2026-08-26 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '000e_acct_rework'
down_revision: str | None = '000d_lp_email_flag'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.drop_column('accounting_answers', 'main_pain_point', schema=SCHEMA)
    op.add_column(
        'accounting_answers',
        sa.Column('willingness_to_pay', sa.String(length=100), nullable=False),
        schema=SCHEMA,
    )
    op.create_table(
        'accounting_pain_selections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('option', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], [f'{SCHEMA}.submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table('accounting_pain_selections', schema=SCHEMA)
    op.drop_column('accounting_answers', 'willingness_to_pay', schema=SCHEMA)
    op.add_column(
        'accounting_answers',
        sa.Column('main_pain_point', sa.String(length=100), nullable=False, server_default='indefinido'),
        schema=SCHEMA,
    )
    op.alter_column('accounting_answers', 'main_pain_point', server_default=None, schema=SCHEMA)
