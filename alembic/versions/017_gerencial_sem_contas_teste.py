"""Contas de teste fora do dashboard gerencial.

A 016 tirava dos numeros so as contas `admin`. Sobravam as contas criadas para
testar o produto, que entram como `beta_user` e inflavam adocao, uso e custo.
Agora uma conta marcada com `role = 'test'` sai de todas as views, custo
inclusive: o que a diretoria acompanha e o custo do medico usando o produto; o
gasto de teste e custo de desenvolvimento.

A marcacao e feita a mao, em producao, pela lista de e-mails que o Ruben revisa:

    UPDATE users SET role = 'test' WHERE email IN (...);

A conta `test` continua entrando e usando o produto, e fica sem o teto semanal,
que so vale para `beta_user` (usage_service.check_limit). Nada e apagado;
voltar a contar e `UPDATE users SET role = 'beta_user'`.

`captacao` passa a filtrar tambem: o lead que virou conta de teste ou admin sai.
Lead que nao virou conta continua contando, porque nao ha como saber se e teste.

As views sao recriadas com CREATE OR REPLACE: as colunas nao mudam, so o WHERE.
O GRANT do role `gerencial_leitura` e as perguntas salvas no Metabase continuam
valendo.

Revision ID: 017_gerencial_sem_contas_teste
Revises: 016_schema_gerencial
Create Date: 2026-09-28 00:00:00.000000
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

# revision identifiers
revision: str = "017_gerencial_sem_contas_teste"
down_revision: str | None = "016_schema_gerencial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# O SQL das views vem da 016, com o filtro trocado: assim o corpo de cada view
# nao e copiado para ca, e o downgrade devolve exatamente o que a 016 criou.
_spec = importlib.util.spec_from_file_location(
    "migration_016", Path(__file__).with_name("016_schema_gerencial.py")
)
_m016 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m016)

_FORA_DO_PAINEL = "COALESCE(u.role, '') NOT IN ('admin', 'test')"

_CAPTACAO = f"""
        SELECT
            lp.name                                      AS landing_page,
            lp.slug                                      AS landing_slug,
            s.created_at                                 AS criado_em,
            {_m016._DIA.format(col="s.created_at")}      AS dia,
            (s.user_id IS NOT NULL)                      AS virou_usuario,
            (s.lgpd_consent_at IS NOT NULL)              AS consentiu_lgpd,
            s.notify_on_availability                     AS quer_aviso
        FROM landing_pages.submissions s
        JOIN landing_pages.landing_pages lp ON lp.id = s.landing_page_id
        LEFT JOIN users u ON u.id = s.user_id
        WHERE {_FORA_DO_PAINEL}
    """


def _views_017() -> dict[str, str]:
    views = {
        nome: corpo.replace(_m016._NAO_ADMIN, _FORA_DO_PAINEL)
        for nome, corpo in _m016.VIEWS.items()
        if _m016._NAO_ADMIN in corpo
    }
    views["captacao"] = _CAPTACAO
    return views


VIEWS: dict[str, str] = _views_017()


def comandos_upgrade() -> list[str]:
    """Separado de `upgrade()` para o teste rodar o MESMO SQL no banco de teste."""
    return [f"CREATE OR REPLACE VIEW gerencial.{nome} AS {corpo}" for nome, corpo in VIEWS.items()]


def comandos_downgrade() -> list[str]:
    return [
        f"CREATE OR REPLACE VIEW gerencial.{nome} AS {_m016.VIEWS[nome]}" for nome in VIEWS
    ]


def upgrade() -> None:
    for sql in comandos_upgrade():
        op.execute(sql)


def downgrade() -> None:
    for sql in comandos_downgrade():
        op.execute(sql)
