"""Marca explicita de submissao sem email vindo da URL (schema landing_pages).

O email do lead chega embutido na URL da LP (prioridade combinada com o
fornecedor do embedding). `email IS NULL` sozinho fica ambiguo com o tempo
-- nao da pra distinguir "fornecedor nao mandou" de "essa LP nem pede
email". Esta flag e setada explicitamente pelo front no momento do POST.

Revision ID: 000d_lp_email_flag
Revises: 000c_lp_email_idx
Create Date: 2026-08-26 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '000d_lp_email_flag'
down_revision: str | None = '000c_lp_email_idx'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.add_column(
        'submissions',
        sa.Column('email_missing', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column('submissions', 'email_missing', schema=SCHEMA)
