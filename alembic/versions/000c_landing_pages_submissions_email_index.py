"""Indice em submissions.email (schema landing_pages).

Email/nome chegam pre-preenchidos via URL (mesmo padrao do EmbedAuthPage
dos outros apps) e viram o jeito de identificar o lead entre submissoes.
Sem indice, essa busca faria sequential scan.

Revision ID: 000c_lp_email_idx
Revises: 000b_lp_tables
Create Date: 2026-08-26 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = '000c_lp_email_idx'
down_revision: str | None = '000b_lp_tables'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.create_index(
        'ix_submissions_email',
        'submissions',
        ['email'],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index('ix_submissions_email', table_name='submissions', schema=SCHEMA)
