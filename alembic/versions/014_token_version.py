"""users.token_version: torna o logout real.

O JWT de sessao e autocontido: depois de "Sair", o cookie HttpOnly seguia valido
ate expirar (ate uma hora), e a unica forma de revogar era desativar o usuario.
Em estacao compartilhada de hospital, o proximo usuario lia o historico do
anterior.

Todo token passa a carregar a versao com que foi emitido (claim `tv`), e
`get_current_user` recusa versao diferente da gravada aqui. `POST /auth/logout`
incrementa a coluna.

`server_default='0'` para as linhas existentes: os tokens em circulacao nao tem
o claim, e ausencia vale 0 — ninguem e deslogado pelo deploy.

Revision ID: 014_token_version
Revises: 013_consent_anonimizavel
Create Date: 2026-09-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "014_token_version"
down_revision: str | None = "013_consent_anonimizavel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
