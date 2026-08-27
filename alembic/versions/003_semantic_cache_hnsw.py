"""Troca o índice do cache semântico de ivfflat para HNSW.

O ivfflat de `semantic_cache` foi criado na migration de baseline, com a tabela
VAZIA. ivfflat calcula os centroides no momento da criação: sem linhas, eles não
representam distribuição nenhuma, e o recall fica degradado até alguém lembrar
de reindexar. `lists = 100` também estava dimensionado para ~10.000 linhas, que
a tabela nunca teve.

HNSW não tem esse problema — constrói o grafo incrementalmente conforme as
linhas entram, sem depender de dados prévios nem de reindexação periódica. Some
a classe inteira de bug, e não só a instância atual.

A troca é feita agora porque a tabela está vazia em produção: um defeito no
`_normalize_prompt` (mandava `max_tokens`, recusado com HTTP 400 pela família
gpt-5) fazia toda escrita ser pulada em silêncio. Com o cache prestes a começar
a encher, este é o único momento em que a migração custa zero.

CONCURRENTLY e autocommit_block: criar índice bloqueando escrita numa tabela do
caminho quente não é aceitável, mesmo que hoje ela esteja vazia.

Revision ID: 003_cache_hnsw
Revises: 002_msg_embeddings
Create Date: 2026-08-27 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = '003_cache_hnsw'
down_revision: str | None = '002_msg_embeddings'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS semantic_cache_embedding_hnsw_idx "
            "ON semantic_cache USING hnsw (prompt_embedding vector_cosine_ops)"
        )
        # Só depois que o novo existe: entre um e outro a busca continua indexada.
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS semantic_cache_embedding_idx")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS semantic_cache_embedding_idx "
            "ON semantic_cache USING ivfflat (prompt_embedding vector_cosine_ops) "
            "WITH (lists = 100)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS semantic_cache_embedding_hnsw_idx")
