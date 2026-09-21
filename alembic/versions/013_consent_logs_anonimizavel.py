"""consent_logs.user_id passa a aceitar NULL, para anonimizar na exclusao de conta.

`DELETE /auth/me` falhava com `ForeignKeyViolationError` em
`consent_logs_user_id_fkey` para todo usuario que passou pelo onboarding — ou
seja, todos. O direito de eliminacao (LGPD art. 18, VI) estava inoperante.

Decisao de 2026-09-21: o consentimento e ANONIMIZADO, nao apagado, como ja se faz
com `audit_logs`. Sai o vinculo com o titular (user_id, IP, user-agent) e fica a
prova de que um consentimento daquele tipo foi dado naquela data. Para isso a
coluna precisa aceitar NULL.

O downgrade apaga os registros ja anonimizados: nao ha como devolver o dono a
eles, e sem isso o `SET NOT NULL` falharia.

Revision ID: 013_consent_anonimizavel
Revises: 012_dea
Create Date: 2026-09-21 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "013_consent_anonimizavel"
down_revision: str | None = "012_dea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("consent_logs", "user_id", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM consent_logs WHERE user_id IS NULL")
    op.alter_column("consent_logs", "user_id", nullable=False)
