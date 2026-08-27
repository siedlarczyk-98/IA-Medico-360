"""Vincula anexos à mensagem em que foram enviados.

Antes não havia relação entre `file_extractions` e `interactions`: o arquivo era
extraído, o texto era injetado no prompt, e o anexo se perdia. Ao reabrir a
conversa sobrava só o texto embutido — o médico não via mais quais exames tinha
mandado.

Nullable de propósito: extrações anteriores a esta mudança não têm mensagem
associada, e não há como inferir qual seria. Também continua nullable para o
intervalo entre o upload e o envio da mensagem, quando a extração já existe mas
a interação ainda não.

`ondelete=SET NULL` e não CASCADE: apagar uma conversa não deve apagar o
arquivo, que pode estar referenciado em outra mensagem ou ser reaproveitado.
A retenção de `file_extractions` é um débito conhecido — ver docs/debitos.md.

Revision ID: 001_file_interaction
Revises: 000h_lp_partners
Create Date: 2026-08-26 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = '001_file_interaction'
down_revision: str | None = '000h_lp_partners'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'file_extractions',
        sa.Column('interaction_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_file_extractions_interaction_id',
        'file_extractions',
        'interactions',
        ['interaction_id'],
        ['id'],
        ondelete='SET NULL',
    )
    # A leitura é sempre "quais anexos desta mensagem", ao montar o histórico.
    op.create_index(
        'ix_file_extractions_interaction_id',
        'file_extractions',
        ['interaction_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_file_extractions_interaction_id', table_name='file_extractions')
    op.drop_constraint(
        'fk_file_extractions_interaction_id', 'file_extractions', type_='foreignkey'
    )
    op.drop_column('file_extractions', 'interaction_id')
