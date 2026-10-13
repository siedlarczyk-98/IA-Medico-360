"""`interno.atividade`: o que cada pessoa fez no app, com o texto da pergunta.

Pedido do Ruben (2026-10-13), para uso DELE no DBeaver: quem perguntou o quê e
quando, quem usou calculadora, quem favoritou notícia, quem entrou.

POR QUE NUM SCHEMA À PARTE, E NÃO EM `gerencial`
O texto da pergunta é clínico — o médico descreve o paciente. O schema
`gerencial` é o que o Metabase lê, e com o MCP do Metabase todo resultado de
consulta passa por um LLM; ali nunca entra texto livre (ver 016). Esta view
fica em `interno`, onde o role `gerencial_leitura` não tem USAGE: o Metabase
não enxerga, nem por acidente. Quem lê `interno` é quem já lê as tabelas do
app — a view não abre acesso novo a ninguém, só junta o que já estava lá.

NÃO dar GRANT deste schema ao `gerencial_leitura` nem a login de BI.

Uma linha por EVENTO, só de quem tem conta (INNER JOIN com `users`):
  pergunta            -> o texto da pergunta, o modo e o produto
  calculadora         -> o nome da calculadora (sem as entradas, que são do paciente)
  noticia_favoritada  -> o título da notícia
  entrada_waid        -> abriu o app pela Waid

Todo mundo entra, equipe inclusive: `role` e `canal_entrada` vêm junto para
filtrar. `dia` é a data em America/Sao_Paulo; `quando` fica em UTC.

Revision ID: 021_interno_atividade
Revises: 020_emails_fora_do_painel
Create Date: 2026-10-13 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "021_interno_atividade"
down_revision: str | None = "020_emails_fora_do_painel"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "interno"
VIEW = "atividade"

# Igual a `prevent_router.ACAO_USO`; migration não importa código da aplicação.
_ACAO_PREVENT = "prevent.calculo"
_DIA = "(e.quando AT TIME ZONE 'America/Sao_Paulo')::date"

_CORPO = f"""
    SELECT
        u.id                 AS user_id,
        u.name               AS nome,
        u.email              AS email,
        u.role               AS role,
        u.canal_entrada      AS canal_entrada,
        e.quando             AS quando,
        {_DIA}               AS dia,
        e.tipo               AS tipo,
        e.detalhe            AS detalhe,
        e.modo               AS modo,
        e.produto            AS produto,
        e.conversa_id        AS conversa_id
    FROM (
        SELECT i.user_id, i.created_at AS quando, 'pergunta' AS tipo,
               i.prompt_text AS detalhe, i.mode AS modo, i.feature AS produto,
               i.conversation_id AS conversa_id
        FROM interactions i

        UNION ALL
        SELECT ce.user_id, ce.created_at, 'calculadora', d.name, NULL, NULL, NULL
        FROM calculators.calculator_executions ce
        JOIN calculators.calculator_definitions d ON d.id = ce.calculator_id

        UNION ALL
        SELECT l.user_id, l.created_at, 'calculadora', 'PREVENT', NULL, NULL, NULL
        FROM audit_logs l
        WHERE l.action = '{_ACAO_PREVENT}'

        UNION ALL
        SELECT f.user_id, f.created_at, 'noticia_favoritada',
               COALESCE(a.rewritten_title, a.original_title), NULL, NULL, NULL
        FROM news.favorites f
        JOIN news.articles a ON a.id = f.article_id

        UNION ALL
        SELECT l.user_id, l.created_at, 'entrada_waid', NULL, NULL, NULL, NULL
        FROM audit_logs l
        WHERE l.action = 'auth.embed'
    ) e
    JOIN users u ON u.id = e.user_id
"""


def comandos_upgrade() -> list[str]:
    """Separado de `upgrade()` para o teste rodar o MESMO SQL no banco de teste."""
    return [
        f"CREATE SCHEMA {SCHEMA}",
        # Por garantia: nada de PUBLIC aqui, mesmo que o padrão do banco mude.
        f"REVOKE ALL ON SCHEMA {SCHEMA} FROM PUBLIC",
        f"CREATE VIEW {SCHEMA}.{VIEW} AS {_CORPO}",
    ]


def comandos_downgrade() -> list[str]:
    return [f"DROP SCHEMA {SCHEMA} CASCADE"]


def upgrade() -> None:
    for sql in comandos_upgrade():
        op.execute(sql)


def downgrade() -> None:
    for sql in comandos_downgrade():
        op.execute(sql)
