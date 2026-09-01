"""Identidade profissional: especialidade com proveniência, profissão e CRM verificado

O PROBLEMA QUE ISTO RESOLVE
`users.specialty` era texto livre, nullable, escrito num único lugar (o
onboarding) e nunca mais editável. Três das quatro classes de usuário jamais o
preenchiam: generalista e graduando não eram perguntados, e quem entra por embed
nasce só com e-mail. O curativo era `ESPECIALIDADE_PISO` no feed de notícias.

A partir daqui a especialidade chega por quatro caminhos (webhook do cadastro,
grupo de acesso da Curseduca, CFM, e o próprio médico) — o que só é seguro
porque `specialty_source` diz de onde veio e `app/medicina/identidade.py` decide
quem pode sobrescrever quem.

POR QUE `specialty` (o rótulo) CONTINUA EXISTINDO
`news.topic_specialties.specialty` casa por STRING com ele. Trocar tudo por slug
exigiria migrar aquela tabela junto, e ela é seed de produto. O rótulo fica como
está; o slug entra ao lado como chave. A FK entre os dois só se paga depois que
o backfill provar que 100% dos valores são canônicos — antes disso seria uma
migration que falha em produção por causa de uma linha de texto livre.

NADA DE BACKFILL AQUI
Todas as colunas nascem nulas. Preencher é trabalho de
`scripts/normalizar_especialidades.py`, que roda em dry-run e é revisável — não
de uma migration que ninguém lê antes de aplicar.

Revision ID: 007_identidade_profissional
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_identidade_profissional"
down_revision: str | None = "006_news_keywords"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# DDL crua em vez de `op.add_column`: esta versão do Alembic não aceita
# `if_not_exists` nesse helper, e a idempotência importa mais aqui do que o
# açúcar sintático — é o mesmo caminho que a 006 usou para a coluna gerada.
COLUNAS: list[tuple[str, str]] = [
    ("specialty_slug", "VARCHAR(80)"),
    # TODAS as especialidades do médico, não só a principal. Duas residências é
    # o caso comum (Clínica Médica é pré-requisito de quase toda residência
    # clínica), e como a especialidade vai definir acesso a conteúdo pago,
    # guardar só uma revogaria em silêncio o direito à outra.
    ("specialties", "JSONB"),
    ("specialty_source", "VARCHAR(20)"),
    ("specialty_updated_at", "TIMESTAMPTZ"),
    ("specialty_rqe", "VARCHAR(20)"),
    ("profissao", "VARCHAR(40)"),
    ("crm_status", "VARCHAR(30)"),
    ("crm_verified_at", "TIMESTAMPTZ"),
    ("cadastro_externo_id", "VARCHAR(64)"),
    ("cfm_payload", "JSONB"),
]


def upgrade() -> None:
    for nome, tipo in COLUNAS:
        op.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {nome} {tipo}")

    # Por ele se agrupa ("quantos cardiologistas temos?") e se varre no backfill.
    op.create_index(
        "ix_users_specialty_slug", "users", ["specialty_slug"], if_not_exists=True
    )

    # Único PARCIAL: nulo não colide com nulo. Sem o `where`, a segunda linha sem
    # cadastro externo já quebraria a constraint — e a imensa maioria da base
    # nunca vai ter esse id.
    op.create_index(
        "uq_users_cadastro_externo_id",
        "users",
        ["cadastro_externo_id"],
        unique=True,
        postgresql_where=sa.text("cadastro_externo_id IS NOT NULL"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_cadastro_externo_id")
    op.execute("DROP INDEX IF EXISTS ix_users_specialty_slug")
    for nome, _ in reversed(COLUNAS):
        op.execute(f"ALTER TABLE users DROP COLUMN IF EXISTS {nome}")
