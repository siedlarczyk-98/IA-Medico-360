"""Módulo de notícias: consolidação no monorepo + taxonomia de temas

Traz o schema `news` para a cadeia de migrations deste repositório e acrescenta
as tabelas do feed personalizado.

POR QUE TUDO AQUI É IDEMPOTENTE
`news.articles` e `news.favorites` JÁ EXISTEM em produção: foram criadas pelo
Alembic de `medico360-news`, um repositório separado que apontava para o mesmo
Postgres. Esta migration precisa rodar tanto num banco que já tem essas tabelas
(produção) quanto num banco vazio (CI, dev, teste) e chegar no mesmo lugar.

Daí `IF NOT EXISTS` em tudo que possa preexistir, e a checagem via `inspector`
antes de mexer em coluna. Um `create_table` cru aqui derrubaria o deploy.

SOBRE O `alembic_version` ÓRFÃO
O repositório antigo mantinha a própria tabela de versões DENTRO do schema
`news`. Depois desta migration, o histórico deste módulo passa a viver na cadeia
principal, e aquela tabela vira uma segunda fonte de verdade sobre o mesmo
banco — a receita de alguém rodar a migration errada um dia. Ela é removida no
fim do upgrade.

Revision ID: 004_news_monorepo
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004_news_monorepo"
down_revision: str | None = "003_cache_hnsw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "news"


def _tem_coluna(tabela: str, coluna: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if tabela not in inspector.get_table_names(schema=SCHEMA):
        return False
    return coluna in {c["name"] for c in inspector.get_columns(tabela, schema=SCHEMA)}


def _tem_tabela(tabela: str) -> bool:
    return tabela in sa.inspect(op.get_bind()).get_table_names(schema=SCHEMA)


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # ── Tabelas herdadas do repositório antigo ───────────────────────────────
    # Criadas só se ausentes (banco novo). Em produção este bloco é no-op.
    if not _tem_tabela("articles"):
        op.create_table(
            "articles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("journal_slug", sa.String(50), nullable=False),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("external_id", sa.String(100), nullable=False),
            sa.Column("doi", sa.String(200), nullable=True),
            sa.Column("source_url", sa.String(1000), nullable=True),
            sa.Column("original_title", sa.Text(), nullable=False),
            sa.Column("original_abstract", sa.Text(), nullable=True),
            sa.Column("authors", sa.Text(), nullable=True),
            sa.Column("published_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rewritten_title", sa.Text(), nullable=True),
            sa.Column("rewritten_body", sa.Text(), nullable=True),
            sa.Column("wp_post_id", sa.Integer(), nullable=True),
            sa.Column("wp_post_url", sa.String(1000), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="collected"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("source", "external_id", name="uq_articles_source_external_id"),
            schema=SCHEMA,
        )
        op.create_index("ix_articles_status", "articles", ["status"], schema=SCHEMA)
        op.create_index(
            "ix_articles_status_published_date",
            "articles",
            ["status", "published_date"],
            schema=SCHEMA,
        )

    # `status` cresceu de 20 para 30 caracteres: `skipped_no_abstract` tem 19 e
    # cabia, mas a folga evita uma migration nova no próximo estado.
    op.execute(f"ALTER TABLE {SCHEMA}.articles ALTER COLUMN status TYPE VARCHAR(30)")

    if not _tem_coluna("articles", "mesh_terms"):
        op.add_column(
            "articles",
            sa.Column("mesh_terms", postgresql.JSONB(), nullable=True),
            schema=SCHEMA,
        )

    if not _tem_coluna("articles", "visible_at"):
        # Quando o item ficou visível no feed — distinto de `published_date`,
        # que é quando o JOURNAL publicou o paper.
        op.add_column(
            "articles",
            sa.Column("visible_at", sa.DateTime(timezone=True), nullable=True),
            schema=SCHEMA,
        )
        # Backfill: o que já estava publicado continua visível, com a data em que
        # foi publicado por nós. Sem isto, todo o acervo existente sumiria do
        # feed no dia do deploy, porque a listagem filtra por `visible_at`.
        op.execute(
            f"UPDATE {SCHEMA}.articles SET visible_at = COALESCE(published_date, created_at) "
            f"WHERE status = 'published' AND visible_at IS NULL"
        )

    op.create_index(
        "ix_articles_visible_at",
        "articles",
        ["visible_at"],
        schema=SCHEMA,
        if_not_exists=True,
    )

    # ── Favoritos: e-mail cru vira usuário de verdade ────────────────────────
    if not _tem_tabela("favorites"):
        op.create_table(
            "favorites",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_email", sa.String(255), nullable=True),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["article_id"], [f"{SCHEMA}.articles.id"], ondelete="CASCADE"),
            schema=SCHEMA,
        )

    if not _tem_coluna("favorites", "user_id"):
        op.add_column(
            "favorites",
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            schema=SCHEMA,
        )
        # Backfill pelo e-mail. Quem favoritou com um e-mail que não corresponde
        # a nenhum usuário fica com user_id nulo e é removido logo abaixo: sem
        # usuário, o favorito não tem dono a quem ser mostrado.
        op.execute(
            f"UPDATE {SCHEMA}.favorites f SET user_id = u.id "
            f"FROM users u WHERE lower(u.email) = lower(f.user_email) AND f.user_id IS NULL"
        )
        op.execute(f"DELETE FROM {SCHEMA}.favorites WHERE user_id IS NULL")
        op.alter_column("favorites", "user_id", nullable=False, schema=SCHEMA)

        # A tabela legada tem uma constraint com ESTE MESMO NOME sobre
        # (user_email, article_id) — o repositório antigo a chamava assim. Sem
        # dropar antes, o ADD CONSTRAINT abaixo falha com DuplicateTableError e
        # derruba o deploy. O índice por e-mail some pelo mesmo motivo: a coluna
        # que ele indexa deixa de existir logo abaixo.
        op.execute(
            f"ALTER TABLE {SCHEMA}.favorites DROP CONSTRAINT IF EXISTS uq_favorites_user_article"
        )
        op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.ix_favorites_user_email")

        op.create_foreign_key(
            "fk_favorites_user_id",
            "favorites",
            "users",
            ["user_id"],
            ["id"],
            source_schema=SCHEMA,
            ondelete="CASCADE",
        )
        op.create_index("ix_favorites_user_id", "favorites", ["user_id"], schema=SCHEMA)
        op.create_unique_constraint(
            "uq_favorites_user_article", "favorites", ["user_id", "article_id"], schema=SCHEMA
        )
        # A coluna antiga sai só depois do backfill bem-sucedido.
        op.drop_column("favorites", "user_email", schema=SCHEMA)

    # ── Taxonomia de temas ───────────────────────────────────────────────────
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("nome_pt", sa.String(160), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
        if_not_exists=True,
    )

    op.create_table(
        "topic_specialties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("specialty", sa.String(120), nullable=False),
        sa.Column("peso", sa.String(20), nullable=False, server_default="relevante"),
        sa.ForeignKeyConstraint(["topic_id"], [f"{SCHEMA}.topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("topic_id", "specialty", name="uq_topic_specialties_topic_specialty"),
        schema=SCHEMA,
        if_not_exists=True,
    )
    op.create_index(
        "ix_topic_specialties_specialty",
        "topic_specialties",
        ["specialty"],
        schema=SCHEMA,
        if_not_exists=True,
    )

    op.create_table(
        "article_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("origem", sa.String(10), nullable=False, server_default="llm"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["article_id"], [f"{SCHEMA}.articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], [f"{SCHEMA}.topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("article_id", "topic_id", name="uq_article_topics_article_topic"),
        schema=SCHEMA,
        if_not_exists=True,
    )
    # Cobre a consulta central do feed: temas do usuário, acima de um score.
    op.create_index(
        "ix_article_topics_topic_score",
        "article_topics",
        ["topic_id", "score"],
        schema=SCHEMA,
        if_not_exists=True,
    )

    op.create_table(
        "user_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], [f"{SCHEMA}.topics.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "topic_id", name="uq_user_topics_user_topic"),
        schema=SCHEMA,
        if_not_exists=True,
    )
    op.create_index(
        "ix_user_topics_user_id", "user_topics", ["user_id"], schema=SCHEMA, if_not_exists=True
    )

    op.create_table(
        "topic_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("specialty", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], [f"{SCHEMA}.articles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], [f"{SCHEMA}.topics.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "article_id", name="uq_topic_feedback_user_article"),
        schema=SCHEMA,
        if_not_exists=True,
    )
    op.create_index(
        "ix_topic_feedback_topic", "topic_feedback", ["topic_id"], schema=SCHEMA, if_not_exists=True
    )

    # A unicidade (user_id, data_ref) é a garantia de idempotência do digest —
    # sem ela, um retry manda o mesmo e-mail duas vezes.
    op.create_table(
        "digest_sends",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_ref", sa.DateTime(timezone=True), nullable=False),
        sa.Column("article_ids", postgresql.JSONB(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "data_ref", name="uq_digest_sends_user_data"),
        schema=SCHEMA,
        if_not_exists=True,
    )

    # ── Histórico órfão do repositório antigo ────────────────────────────────
    # A partir daqui, a única fonte de verdade sobre migrations deste banco é a
    # cadeia principal. Deixar as duas conviverem convida a rodar a errada.
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.alembic_version")


def downgrade() -> None:
    # As tabelas novas do feed saem. `articles` e `favorites` NÃO são removidas:
    # elas antecedem esta migration e carregam o acervo de produção — um
    # downgrade que apagasse conteúdo publicado seria pior que o problema que
    # motivou o downgrade.
    for tabela in (
        "digest_sends",
        "topic_feedback",
        "user_topics",
        "article_topics",
        "topic_specialties",
        "topics",
    ):
        op.drop_table(tabela, schema=SCHEMA, if_exists=True)

    op.drop_index("ix_articles_visible_at", "articles", schema=SCHEMA, if_exists=True)
    op.drop_column("articles", "visible_at", schema=SCHEMA)
    op.drop_column("articles", "mesh_terms", schema=SCHEMA)
