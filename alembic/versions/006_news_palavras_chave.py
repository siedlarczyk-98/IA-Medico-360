"""Palavras-chave do médico + índice de busca textual nos destaques

Um EIXO SEPARADO dos temas, e não "mais um tema".

POR QUE NÃO PODE SER UM TEMA
O tagger classifica os artigos escolhendo de uma lista fechada (`news.topics`).
Um tema criado pelo usuário nunca estaria nessa lista, então nenhum artigo
jamais o receberia: o médico veria o tema marcado na tela e receberia zero
destaques para sempre, sem erro, sem log, sem nada. Falha silenciosa, que é
exatamente o padrão que já deixou o cache semântico meses desligado aqui.

Palavra-chave casa contra o TEXTO do artigo. Tema casa contra o que o tagger
atribuiu. Mecanismos diferentes, unidos só na hora de montar o feed.

SOBRE OS PESOS DO tsvector
'A' no título, 'B' no corpo. É o que separa "artigo SOBRE amiloidose" de
"artigo que menciona amiloidose uma vez": `ts_rank` põe o primeiro muito acima,
e um piso de rank (`NEWS_KEYWORD_RANK_MINIMO`) corta o segundo. Sem os pesos, a
única alternativa seria buscar num pedaço truncado do corpo, o que é pior e mais
frágil.

A busca é sobre `rewritten_*` (português, escrito pelo nosso redator) e não
sobre `original_*` (inglês, vindo do PubMed): o médico digita "amiloidose", não
"amyloidosis".

Revision ID: 006_news_keywords
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006_news_keywords"
down_revision: str | None = "005_news_taxonomia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "news"

# Coluna GERADA, não preenchida por trigger nem por código: o Postgres a mantém
# em dia sozinho a cada UPDATE do título ou do corpo. `to_tsvector` com a
# configuração passada como constante é IMMUTABLE, que é o que permite isto.
BUSCA_EXPR = (
    "setweight(to_tsvector('portuguese', coalesce(rewritten_title, '')), 'A') || "
    "setweight(to_tsvector('portuguese', coalesce(rewritten_body,  '')), 'B')"
)


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.articles "
        f"ADD COLUMN IF NOT EXISTS busca_tsv tsvector "
        f"GENERATED ALWAYS AS ({BUSCA_EXPR}) STORED"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_articles_busca_tsv "
        f"ON {SCHEMA}.articles USING GIN (busca_tsv)"
    )

    op.create_table(
        "user_keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Guardado já normalizado (trim + lower) pelo serviço. A unicidade
        # depende disso: sem normalizar, "Amiloidose" e "amiloidose" seriam duas
        # linhas que trazem exatamente o mesmo conteúdo.
        sa.Column("termo", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "termo", name="uq_user_keywords_user_termo"),
        schema=SCHEMA,
        if_not_exists=True,
    )
    op.create_index(
        "ix_user_keywords_user_id", "user_keywords", ["user_id"], schema=SCHEMA, if_not_exists=True
    )
    # Sem filtro de usuário: é a consulta que responde "o que os médicos estão
    # procurando e a taxonomia não cobre?" — a lista de compras dos temas que
    # faltam. Hoje isso só teria resposta por palpite.
    op.create_index(
        "ix_user_keywords_termo", "user_keywords", ["termo"], schema=SCHEMA, if_not_exists=True
    )


def downgrade() -> None:
    op.drop_table("user_keywords", schema=SCHEMA, if_exists=True)
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_articles_busca_tsv")
    op.execute(f"ALTER TABLE {SCHEMA}.articles DROP COLUMN IF EXISTS busca_tsv")
