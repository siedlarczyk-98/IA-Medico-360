"""Índice semântico das mensagens, para contexto entre conversas da mesma pasta.

Tabela nova em vez de coluna vetorial em `interactions`: uma interação vira DOIS
trechos indexáveis (a pergunta e a resposta), e uma coluna só não comportaria os
dois. Separar também permite reindexar sem tocar no histórico e apagar o índice
inteiro sem risco para o dado de verdade.

`content` é duplicado aqui de propósito. O trecho recuperado precisa voltar
junto com a similaridade, e ir buscar o texto em `interactions`/
`interaction_responses` depois exigiria uma segunda consulta no caminho quente,
por linha recuperada.

Sem índice ivfflat, ao contrário de `semantic_cache`: ivfflat é aproximado e
precisa de volume para ser treinado bem. Aqui a busca é sempre dentro de UMA
pasta de UM usuário — o conjunto filtrado é pequeno e a varredura exata é tanto
mais correta quanto rápida o suficiente. Ver docs/debitos.md.

Revision ID: 002_msg_embeddings
Revises: 001_file_interaction
Create Date: 2026-08-27 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers
revision: str = '002_msg_embeddings'
down_revision: str | None = '001_file_interaction'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'message_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        # CASCADE: um embedding de mensagem apagada não tem sentido, e mantê-lo
        # devolveria ao modelo um trecho que já não existe na conversa.
        sa.Column('interaction_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['interaction_id'], ['interactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # A busca sempre filtra por dono antes de comparar vetores — o filtro é a
    # garantia de isolamento, não uma otimização.
    op.create_index(
        'ix_message_embeddings_user_conversation',
        'message_embeddings',
        ['user_id', 'conversation_id'],
    )
    # Usado para saber o que ainda falta indexar numa conversa.
    op.create_index(
        'ix_message_embeddings_interaction',
        'message_embeddings',
        ['interaction_id', 'role'],
    )


def downgrade() -> None:
    op.drop_index('ix_message_embeddings_interaction', table_name='message_embeddings')
    op.drop_index('ix_message_embeddings_user_conversation', table_name='message_embeddings')
    op.drop_table('message_embeddings')
