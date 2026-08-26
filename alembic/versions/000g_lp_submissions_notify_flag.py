"""Adiciona 'quero ser avisado quando disponivel' na submissao (schema landing_pages).

Nasceu no pedido de calculadora (medico logado), mas fica no submissions
generico — mesma logica do user_id (000f): nao atrapalha accounting/finance,
que so nao usam a coluna.

Revision ID: 000g_lp_notify_flag
Revises: 000f_lp_user_link
Create Date: 2026-08-26 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '000g_lp_notify_flag'
down_revision: str | None = '000f_lp_user_link'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = 'landing_pages'


def upgrade() -> None:
    op.add_column(
        'submissions',
        sa.Column('notify_on_availability', sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column('submissions', 'notify_on_availability', schema=SCHEMA)
