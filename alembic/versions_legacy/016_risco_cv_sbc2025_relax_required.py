"""Relax required flag on risco_cv_sbc2025 fields to allow partial (early-exit) execute payloads

Revision ID: 016_risco_cv_relax_required
Revises: 015_calculators_schema
Create Date: 2026-07-01
"""
from alembic import op

revision = "016_risco_cv_relax_required"
down_revision = "015_calculators_schema"
branch_labels = None
depends_on = None

SCHEMA = "calculators"

# Todos os campos abaixo são lidos via `.get()` ou dentro de bloco condicional em
# calculate() (app/calculators/formulas/cardiologia/risco_cv_sbc2025.py) — apenas
# `idade` e `sexo` são acessados diretamente e permanecem obrigatórios.
FIELDS_TO_RELAX = [
    "ct_mgdl", "hdl_mgdl", "ldl_mgdl", "sbp_mmhg", "bmi", "egfr",
    "fumante", "antihtn_use", "statin_use", "hipertensao",
    "evento_cv_previo", "doenca_aterosclerotica_significativa",
    "hipercolesterolemia_familiar", "diabetes",
]


def upgrade() -> None:
    keys = ", ".join(f"'{k}'" for k in FIELDS_TO_RELAX)
    op.execute(f"""
        UPDATE {SCHEMA}.calculator_fields
        SET required = false
        WHERE key IN ({keys})
          AND calculator_id = (
              SELECT id FROM {SCHEMA}.calculator_definitions WHERE slug = 'risco_cv_sbc2025'
          )
    """)


def downgrade() -> None:
    keys = ", ".join(f"'{k}'" for k in FIELDS_TO_RELAX)
    op.execute(f"""
        UPDATE {SCHEMA}.calculator_fields
        SET required = true
        WHERE key IN ({keys})
          AND calculator_id = (
              SELECT id FROM {SCHEMA}.calculator_definitions WHERE slug = 'risco_cv_sbc2025'
          )
    """)
