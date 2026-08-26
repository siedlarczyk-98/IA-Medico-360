"""Cria o schema landing_pages.

Isola os dados de captacao de leads (preenchimento de LPs) do schema
`public` de dominio clinico. As tabelas serao adicionadas em migrations
seguintes.

Revision ID: 000a_lp_schema
Revises: 000_baseline
Create Date: 2026-08-25 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = '000a_lp_schema'
down_revision: str | None = '000_baseline'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS landing_pages")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS landing_pages CASCADE")
