"""Evolução clínica na pasta: contexto que o médico escreve, não que o sistema infere

O PROBLEMA QUE ISTO RESOLVE
Uma pasta era só um nome. O contexto entre conversas dela existia
(`folder_context_service`), mas é recuperado por SIMILARIDADE e chega ao modelo
marcado como "material de APOIO, pode ser de outro paciente — não trate como
parte do caso atual". Esse aviso é correto para o que aquele mecanismo faz.

Só que a evolução de um paciente é o oposto disso: é o caso atual, escrita pelo
médico, e vale como verdade sobre ele. Injetá-la pelo caminho antigo entregaria
ao modelo um texto autoritativo carimbado com "não confie nisto".

Daí a coluna própria: `folders.clinical_context` é contexto DECLARADO, entra em
todas as mensagens da pasta na íntegra, e é formatado com marcação própria em
`folder_context_service.formatar_bloco_evolucao`.

POR QUE UM CAMPO ÚNICO, E NÃO UMA LINHA DO TEMPO
Uma evolução clínica de verdade é cronológica, e uma tabela de entradas datadas
seria mais fiel. Ficou como campo único editável por decisão de escopo: o estado
ATUAL do paciente é o que o modelo precisa, e o histórico de como se chegou nele
é revisão do médico, não contexto de prompt. Se virar linha do tempo depois,
esta coluna é o "estado atual" derivado dela — não vira lixo.

NASCE NULA, SEM BACKFILL
Não há o que preencher: é informação que só o médico tem. Pasta sem evolução é o
caso normal e continua funcionando exatamente como antes.

Revision ID: 009_folder_evolucao_clinica
"""

from collections.abc import Sequence

from alembic import op

revision: str = "009_folder_evolucao_clinica"
down_revision: str | None = "008_waid_uuid"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# TEXT e não VARCHAR(n): o teto de tamanho é decisão de PRODUTO e vive na API
# (`MAX_CHARS_EVOLUCAO`), onde pode mudar sem uma migration. Um limite no banco
# aqui só produziria erro 500 no lugar de um 422 explicativo.
#
# DDL crua com `IF NOT EXISTS` pelo mesmo motivo da 007: idempotência vale mais
# que o açúcar do `op.add_column`, que nesta versão do Alembic não a oferece.
def upgrade() -> None:
    op.execute("ALTER TABLE folders ADD COLUMN IF NOT EXISTS clinical_context TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS clinical_context")
