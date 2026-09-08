"""Índices que faltavam em audit_logs e interactions

O PROBLEMA QUE ISTO RESOLVE
Três consultas do dia a dia rodavam sem índice de suporte. Hoje isso não dói —
`audit_logs` tem ~550 linhas e `interactions` ~38 — e é justamente por isso que
passou despercebido: o Seq Scan de uma tabela pequena é rápido. O custo cresce
linearmente com o uso, e o sintoma (a vigilância ficando lenta, o histórico
demorando a abrir) aparece devagar demais para alguém associar à causa.

1. `audit_logs (action, created_at)`
   `vigilancia_service` roda `max(created_at) WHERE action = ...` duas vezes por
   rodada, a cada 6 horas — uma para o expurgo LGPD, outra para o digest de
   notícias. Sem índice, é Seq Scan da tabela de auditoria inteira, que é
   escrita UMA VEZ POR INTERAÇÃO em três serviços. É a tabela que mais cresce
   no sistema depois de `interactions`.

   O comentário em `vigilancia_agendada` afirmava que "as três consultas são
   três COUNT indexados — o custo de rodar é irrelevante". Não era verdade para
   estas duas: não havia índice em `action` nem em `created_at`.

   Composto e nesta ordem: `action` filtra, `created_at` agrega. O Postgres
   resolve o `max()` com um Index Only Scan pegando a última entrada do grupo,
   sem ler a tabela.

2. `audit_logs (user_id)`
   `auth_repository.apagar_dados_do_usuario` faz
   `UPDATE audit_logs SET user_id = NULL WHERE user_id = :id` — anonimização no
   fluxo de exclusão de conta da LGPD. Sem índice, Seq Scan. É uma operação que
   precisa terminar dentro do tempo de uma requisição.

3. `interactions (conversation_id, status, started_at)`
   `conversation_history.load_history` roda em TODA MENSAGEM do orquestrador:
   `WHERE conversation_id = ? AND status = 'completed'
    ORDER BY started_at DESC LIMIT 40`.

   Os índices existentes cobrem o WHERE, mas nenhum cobre o `ORDER BY
   started_at`: o Postgres precisa buscar todas as interações da conversa e
   ordená-las em memória para pegar as 40 mais recentes. Numa conversa curta é
   irrelevante; numa conversa longa — o médico que trabalha um caso por semanas
   — o custo cresce com o histórico e é pago a cada nova mensagem.

   Com o índice, vira Index Scan descendente que lê exatamente 40 linhas.

CONCURRENTLY NÃO É USADO
Seria o certo para tabelas grandes em produção, mas exige rodar fora de
transação, e o Alembic envolve cada migration numa. Com as tabelas no tamanho
atual (centenas de linhas), o lock é de milissegundos. Se este projeto chegar a
milhões de linhas antes de alguém reindexar, o índice precisará ser criado à
mão com `CREATE INDEX CONCURRENTLY`.

Revision ID: 011_indices_auditoria
"""

from collections.abc import Sequence

from alembic import op

revision: str = "011_indices_auditoria"
down_revision: str | None = "010_folder_tipo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDICES: list[tuple[str, str, str]] = [
    ("ix_audit_logs_action_created_at", "audit_logs", "action, created_at"),
    ("ix_audit_logs_user_id", "audit_logs", "user_id"),
    (
        "ix_interactions_conversation_status_started_at",
        "interactions",
        "conversation_id, status, started_at",
    ),
]


def upgrade() -> None:
    for nome, tabela, colunas in INDICES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {nome} ON {tabela} ({colunas})")


def downgrade() -> None:
    for nome, _tabela, _colunas in INDICES:
        op.execute(f"DROP INDEX IF EXISTS {nome}")
