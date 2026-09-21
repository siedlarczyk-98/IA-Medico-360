"""otp_codes.code passa a guardar o HMAC do codigo, nao o codigo.

O codigo de acesso por e-mail ficava em texto puro: quem lesse a tabela (dump,
replica, log de consulta) entrava na conta de qualquer medico com codigo pendente.
A coluna passa de VARCHAR(6) para VARCHAR(64), que e o tamanho do HMAC-SHA256 em
hexadecimal (ver `auth_service._resumo_do_codigo`).

Os codigos pendentes no momento do deploy sao INVALIDADOS: estao em texto puro, e
o codigo novo os compararia com um HMAC — nunca bateriam. Quem estava no meio de um
login pede outro codigo; a validade deles e de 10 minutos de qualquer forma.

Revision ID: 015_otp_code_hmac
Revises: 014_token_version
Create Date: 2026-09-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "015_otp_code_hmac"
down_revision: str | None = "014_token_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE otp_codes SET used = true WHERE used = false")
    op.alter_column("otp_codes", "code", type_=sa.String(64), existing_nullable=False)


def downgrade() -> None:
    # Um HMAC de 64 caracteres nao cabe em 6, e nao ha como recuperar o codigo.
    op.execute("DELETE FROM otp_codes")
    op.alter_column("otp_codes", "code", type_=sa.String(6), existing_nullable=False)
