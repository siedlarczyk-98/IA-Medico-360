"""Liga submissions ao usuario logado (schema landing_pages -> public.users).

A LP de calculadoras deixou de ser uma pagina publica: virou uma tela dentro
do modulo de calculadoras, usada por medico autenticado. Sem isso, submission
so identifica por nome/email soltos (pensado pra lead anonimo de embed), o
que nao da pra confiar como identidade de conta nem deduplicar direito.

user_id fica nullable pra nao quebrar o fluxo anonimo que accounting/finance
ainda usam (embed sem login).

Revision ID: 000f_lp_user_link
Revises: 000e_acct_rework
Create Date: 2026-08-26 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '000f_lp_user_link'
down_revision: str | None = '000e_acct_rework'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.add_column(
        'submissions',
        sa.Column('user_id', sa.UUID(), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        'fk_lp_submissions_user_id',
        'submissions',
        'users',
        ['user_id'],
        ['id'],
        source_schema=SCHEMA,
        referent_schema='public',
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_lp_submissions_user_id',
        'submissions',
        ['user_id'],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index('ix_lp_submissions_user_id', table_name='submissions', schema=SCHEMA)
    op.drop_constraint('fk_lp_submissions_user_id', 'submissions', schema=SCHEMA, type_='foreignkey')
    op.drop_column('submissions', 'user_id', schema=SCHEMA)
