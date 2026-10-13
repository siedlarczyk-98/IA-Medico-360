"""Lista de e-mails que não contam no painel da diretoria.

A 019 tira a equipe pelo domínio do e-mail (cursosactive.com.br, paciente360...)
e pelo `role = 'test'`. Sobra a equipe que usa e-mail PESSOAL (gmail, outlook):
nem o domínio a denuncia, nem o role, porque muitas dessas pessoas não têm conta
no app — só cadastro de teste na Waid. Em 2026-10-13 eram quatro.

`emails_fora_do_painel` resolve sem migration nova a cada caso: quem está nela
sai de `usuarios`, `acesso` e `usuarios_lista`, tenha ou não conta. Comparação
em minúsculas, contra o e-mail da Waid e o da conta.

A tabela nasce VAZIA: os e-mails são pessoais e não vão para o repositório.
Entram por INSERT em produção (docs/dashboard-gerencial.md):

    INSERT INTO emails_fora_do_painel (email, motivo) VALUES ('fulano@gmail.com', 'equipe');

O role do Metabase não lê a tabela; as views leem com os direitos do dono.

Revision ID: 020_emails_fora_do_painel
Revises: 019_prevent_conta_como_uso
Create Date: 2026-10-13 00:00:00.000000
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "020_emails_fora_do_painel"
down_revision: str | None = "019_prevent_conta_como_uso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_spec = importlib.util.spec_from_file_location(
    "migration_019", Path(__file__).with_name("019_prevent_conta_como_uso.py")
)
_m019 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m019)

TABELA = "emails_fora_do_painel"

_FORA_DA_LISTA = f"""NOT EXISTS (
            SELECT 1 FROM {TABELA} x
            WHERE x.email = lower(m.email) OR x.email = lower(u.email)
        )"""


def _sem_os_da_lista(corpo: str) -> str:
    assert corpo.count(_m019._FORA) == 1, "o filtro da 019 mudou"
    return corpo.replace(_m019._FORA, f"{_m019._FORA}\n        AND {_FORA_DA_LISTA}")


# Só as três views de PESSOAS. `calculadoras` (uso) fica como na 019.
_DE_PESSOAS = ("usuarios", _m019._m018.VIEW_ACESSO, _m019._m018.VIEW_LISTA)
VIEWS: dict[str, str] = {nome: _sem_os_da_lista(_m019.VIEWS[nome]) for nome in _DE_PESSOAS}
_VIEWS_019 = {nome: _m019.VIEWS[nome] for nome in _DE_PESSOAS}


def comandos_upgrade() -> list[str]:
    """Só as views; a tabela vem do `create_all` no teste e do `upgrade()` em produção."""
    return _m019._recriar(VIEWS)


def comandos_downgrade() -> list[str]:
    return _m019._recriar(_VIEWS_019)


def upgrade() -> None:
    op.create_table(
        TABELA,
        sa.Column("email", sa.String(255), primary_key=True),
        sa.Column("motivo", sa.String(255), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("email = lower(email)", name="ck_emails_fora_do_painel_minusculo"),
    )
    for sql in comandos_upgrade():
        op.execute(sql)


def downgrade() -> None:
    for sql in comandos_downgrade():
        op.execute(sql)
    op.drop_table(TABELA)
