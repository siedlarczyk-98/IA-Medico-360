"""Identidade do aluno na Waid como chave estável

POR QUE O E-MAIL NÃO SERVE DE CHAVE
A doc de integração da Waid é explícita: "uuid — Identificador do aluno na Waid.
Estável — use-o como chave, e não o e-mail." Hoje `users.email` é a chave única e
a única forma de reencontrar alguém. Se o médico trocar de e-mail na Waid, o
próximo login não o encontra: nasce uma conta nova, e o histórico de conversas,
pastas e especialidade fica órfão — sem erro, sem log, sem ninguém perceber.

NULLABLE, E CONTINUA ASSIM
Nem todo usuário vem da Waid: OTP e convite criam conta sem passar por lá. E os
que já existem só ganham o uuid quando logarem de novo pelo embed — o backfill é
preguiçoso, feito por `auth_service.get_or_create_por_identidade_waid`, um login
por vez. Não há script: forçar o preenchimento exigiria consultar a Waid por
e-mail para toda a base, e o dado chega sozinho.

ÚNICO PARCIAL
`WHERE waid_uuid IS NOT NULL`, como o `cadastro_externo_id` da 007: nulo não
colide com nulo, e a imensa maioria das linhas fica nula por um tempo.

Revision ID: 008_waid_uuid
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008_waid_uuid"
down_revision: str | None = "007_identidade_profissional"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS waid_uuid VARCHAR(64)")
    op.create_index(
        "uq_users_waid_uuid",
        "users",
        ["waid_uuid"],
        unique=True,
        postgresql_where=sa.text("waid_uuid IS NOT NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_waid_uuid")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS waid_uuid")
