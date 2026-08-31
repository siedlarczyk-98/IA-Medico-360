"""Seed da taxonomia de temas do feed de notícias

O conteúdo vive em `app/news/taxonomia.py`, não aqui: ele é revisável por quem
não lê Alembic, é testável, e vai mudar com base no que `news.topic_feedback`
mostrar. Esta migration só o aplica ao banco.

IDEMPOTENTE POR CONSTRUÇÃO
Roda com `ON CONFLICT DO NOTHING` em ambas as tabelas, então reaplicar não
duplica nem sobrescreve. Um tema que já existe mantém o `id` — o que importa,
porque `news.user_topics` aponta para ele e re-seedar não pode apagar a escolha
de ninguém.

O QUE ESTA MIGRATION NÃO FAZ
Não remove temas que sumiram do arquivo. Remover apagaria em cascata as escolhas
dos usuários e o histórico de `article_topics`. Para aposentar um tema, marque
`ativo = false` numa migration própria: ele some da tela de escolha e para de ser
atribuído, sem destruir o passado.

Revision ID: 005_news_taxonomia
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.news.taxonomia import TAXONOMIA

revision: str = "005_news_taxonomia"
down_revision: str | None = "004_news_monorepo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "news"


def upgrade() -> None:
    conn = op.get_bind()

    for tema in TAXONOMIA:
        conn.execute(
            sa.text(
                f"INSERT INTO {SCHEMA}.topics (id, slug, nome_pt, ativo, created_at) "
                "VALUES (gen_random_uuid(), :slug, :nome, true, now()) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {"slug": tema["slug"], "nome": tema["nome"]},
        )

        for especialidade, peso in tema["especialidades"]:
            conn.execute(
                sa.text(
                    f"INSERT INTO {SCHEMA}.topic_specialties (id, topic_id, specialty, peso) "
                    f"SELECT gen_random_uuid(), t.id, :esp, :peso FROM {SCHEMA}.topics t "
                    "WHERE t.slug = :slug "
                    "ON CONFLICT (topic_id, specialty) DO NOTHING"
                ),
                {"slug": tema["slug"], "esp": especialidade, "peso": peso},
            )


def downgrade() -> None:
    conn = op.get_bind()
    slugs = [t["slug"] for t in TAXONOMIA]
    # Só remove os temas semeados por esta migration, e a cascata leva junto os
    # vínculos. Temas criados depois, à mão, permanecem.
    conn.execute(
        sa.text(f"DELETE FROM {SCHEMA}.topics WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
