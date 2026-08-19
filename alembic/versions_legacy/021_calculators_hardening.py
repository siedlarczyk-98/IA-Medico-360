"""Calculators hardening: max_length on text fields, single-active-version guarantee,
history index covering ORDER BY

Revision ID: 021_calculators_hardening
Revises: 020_fix_display_order
Create Date: 2026-08-18
"""
import sqlalchemy as sa

from alembic import op

revision = "021_calculators_hardening"
down_revision = "020_fix_display_order"
branch_labels = None
depends_on = None

SCHEMA = "calculators"


def upgrade() -> None:
    # Teto de caracteres por campo `text` (NULL = usa o default global de settings).
    op.add_column(
        "calculator_fields",
        sa.Column("max_length", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )

    # `get_active_version` assume no maximo uma versao ativa por calculadora
    # (RN-CALC-SCHEMA-005), mas nada garantia isso no banco: um seed que esquece
    # de desativar a versao anterior fazia a calculadora responder 500.
    # Desativa duplicatas preexistentes mantendo a de maior version_number.
    op.execute(f"""
        UPDATE {SCHEMA}.calculator_versions v
        SET is_active = false
        WHERE v.is_active
          AND v.version_number < (
              SELECT MAX(v2.version_number)
              FROM {SCHEMA}.calculator_versions v2
              WHERE v2.calculator_id = v.calculator_id AND v2.is_active
          )
    """)
    op.drop_index("ix_calculator_versions_calculator_active", table_name="calculator_versions", schema=SCHEMA)
    op.create_index(
        "uq_calculator_versions_one_active",
        "calculator_versions",
        ["calculator_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        schema=SCHEMA,
    )

    # `list_executions` filtra (calculator_id, user_id) e ordena por created_at
    # DESC; o indice antigo nao cobria a ordenacao, forcando sort a cada consulta.
    op.drop_index("ix_calculator_executions_calculator_user", table_name="calculator_executions", schema=SCHEMA)
    op.create_index(
        "ix_calculator_executions_calculator_user_created_at",
        "calculator_executions",
        ["calculator_id", "user_id", sa.text("created_at DESC")],
        schema=SCHEMA,
    )
    # Nenhuma query do modulo usa (user_id, created_at) isoladamente.
    op.drop_index("ix_calculator_executions_user_created_at", table_name="calculator_executions", schema=SCHEMA)


def downgrade() -> None:
    op.create_index(
        "ix_calculator_executions_user_created_at",
        "calculator_executions",
        ["user_id", "created_at"],
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_calculator_executions_calculator_user_created_at",
        table_name="calculator_executions",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_calculator_executions_calculator_user",
        "calculator_executions",
        ["calculator_id", "user_id"],
        schema=SCHEMA,
    )

    op.drop_index("uq_calculator_versions_one_active", table_name="calculator_versions", schema=SCHEMA)
    op.create_index(
        "ix_calculator_versions_calculator_active",
        "calculator_versions",
        ["calculator_id", "is_active"],
        schema=SCHEMA,
    )

    op.drop_column("calculator_fields", "max_length", schema=SCHEMA)
