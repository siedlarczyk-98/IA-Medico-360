"""Standardize timestamp columns: createdat/updatedat -> created_at/updated_at

Padroniza o nome das colunas de auditoria em todo o schema para o padrão
snake_case `created_at` / `updated_at` (a maioria das tabelas usava `createdat`
/ `updatedat`). Renomeia também os índices que referenciavam esses nomes.

Rename de coluna no Postgres preserva os dados (ALTER TABLE ... RENAME COLUMN);
ainda assim, rodar em produção com backup e janela de deploy sincronizada com o
frontend (o contrato JSON da API muda de `createdat` para `created_at`).

Revision ID: 018_standardize_timestamps
Revises: 017_calculator_favorites
Create Date: 2026-07-01
"""
from alembic import op

revision = "018_standardize_timestamps"
down_revision = "017_calculator_favorites"
branch_labels = None
depends_on = None

CALC_SCHEMA = "calculators"

# (schema, tabela): tabelas com coluna createdat
PUBLIC_CREATEDAT = [
    "company", "users", "folders", "conversations", "interactions",
    "interaction_responses", "pharma_alerts", "interaction_medications",
    "pubmed_validations", "audit_logs", "consent_logs", "model_pricing",
]
PUBLIC_UPDATEDAT = ["company", "users", "user_preferences", "folders", "conversations", "model_pricing"]

CALC_CREATEDAT = [
    "specialties", "calculator_definitions", "calculator_fields",
    "calculator_versions", "calculator_favorites", "calculator_executions",
]
CALC_UPDATEDAT = ["specialties", "calculator_definitions", "calculator_fields"]

# (schema, nome_antigo, nome_novo)
INDEX_RENAMES = [
    (None, "ix_folders_user_createdat", "ix_folders_user_created_at"),
    (None, "ix_interactions_user_createdat", "ix_interactions_user_created_at"),
    (None, "ix_conversations_user_status_updatedat", "ix_conversations_user_status_updated_at"),
    # Índice criado por migration de performance antiga (não declarado no model).
    (None, "ix_audit_logs_createdat", "ix_audit_logs_created_at"),
    (CALC_SCHEMA, "ix_calculator_executions_user_createdat", "ix_calculator_executions_user_created_at"),
]


def _rename_column(table: str, old: str, new: str, schema: str | None = None) -> None:
    op.alter_column(table, old, new_column_name=new, schema=schema)


def _rename_index(schema: str | None, old: str, new: str) -> None:
    qualified = f"{schema}.{old}" if schema else old
    op.execute(f'ALTER INDEX {qualified} RENAME TO {new}')


def upgrade() -> None:
    for table in PUBLIC_CREATEDAT:
        _rename_column(table, "createdat", "created_at")
    for table in PUBLIC_UPDATEDAT:
        _rename_column(table, "updatedat", "updated_at")
    for table in CALC_CREATEDAT:
        _rename_column(table, "createdat", "created_at", schema=CALC_SCHEMA)
    for table in CALC_UPDATEDAT:
        _rename_column(table, "updatedat", "updated_at", schema=CALC_SCHEMA)
    for schema, old, new in INDEX_RENAMES:
        _rename_index(schema, old, new)


def downgrade() -> None:
    for schema, old, new in INDEX_RENAMES:
        _rename_index(schema, new, old)
    for table in CALC_UPDATEDAT:
        _rename_column(table, "updated_at", "updatedat", schema=CALC_SCHEMA)
    for table in CALC_CREATEDAT:
        _rename_column(table, "created_at", "createdat", schema=CALC_SCHEMA)
    for table in PUBLIC_UPDATEDAT:
        _rename_column(table, "updated_at", "updatedat")
    for table in PUBLIC_CREATEDAT:
        _rename_column(table, "created_at", "createdat")
