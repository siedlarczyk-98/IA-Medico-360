"""Tipo da pasta: clínica ou não, para o contexto ser marcado pelo que ele é

O PROBLEMA QUE ISTO RESOLVE
A 009 acrescentou `folders.clinical_context` supondo que toda pasta é de um
paciente. Não é: uma pasta pode ser "Artigos para ler", "Residência R3" ou
"Gestão do consultório", e nessas o campo pedia "Evolução do paciente" — rótulo
que não significa nada ali.

O efeito ruim não estava só na tela. `formatar_bloco_evolucao` injeta o texto
com a marcação "[Evolução do paciente / contexto do caso ... Vale como parte do
caso atual.]". Numa pasta de estudos, isso faz o modelo ler um plano de leitura
como se fosse a evolução de um paciente — e responder clinicamente sobre algo
que não é um caso.

`folder_kind` distingue os dois, e a marcação do bloco passa a seguir o tipo.

POR QUE VARCHAR COM CHECK, E NÃO UM ENUM DO POSTGRES
Um tipo ENUM exigiria `ALTER TYPE` a cada valor novo, e a lista de tipos é
decisão de produto que tende a crescer (o próximo candidato é algo como
"protocolo"). O CHECK dá a mesma garantia e sai do caminho quando a lista mudar.

O DEFAULT É 'clinical', E ISSO É DELIBERADO
As pastas que já existem foram criadas quando o campo era descrito como evolução
de paciente. Quem preencheu, preencheu isso. Assumir 'clinical' preserva o
sentido do que já está gravado; assumir o contrário reclassificaria dado clínico
existente como não-clínico e mudaria a marcação enviada ao modelo.

Revision ID: 010_folder_tipo
"""

from collections.abc import Sequence

from alembic import op

revision: str = "010_folder_tipo"
down_revision: str | None = "009_folder_evolucao_clinica"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# NOT NULL com DEFAULT: nenhuma linha existente fica sem tipo, e nenhum caminho
# de escrita futuro consegue gravar uma pasta sem ele. Em Postgres 11+ um
# DEFAULT constante não reescreve a tabela.
def upgrade() -> None:
    op.execute(
        "ALTER TABLE folders ADD COLUMN IF NOT EXISTS folder_kind "
        "VARCHAR(20) NOT NULL DEFAULT 'clinical'"
    )
    # `NOT VALID` evita varrer a tabela inteira segurando lock: o CHECK passa a
    # valer para toda escrita nova imediatamente, e as linhas já existentes são
    # cobertas pelo DEFAULT acima, que só produz valores válidos.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'ck_folders_folder_kind'
            ) THEN
                ALTER TABLE folders ADD CONSTRAINT ck_folders_folder_kind
                CHECK (folder_kind IN ('clinical', 'general')) NOT VALID;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE folders DROP CONSTRAINT IF EXISTS ck_folders_folder_kind")
    op.execute("ALTER TABLE folders DROP COLUMN IF EXISTS folder_kind")
