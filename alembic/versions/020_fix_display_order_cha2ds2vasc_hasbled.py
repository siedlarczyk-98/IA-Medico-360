"""Fix display_order tie between tev_previo and doenca_vascular on cha2ds2vasc_hasbled

Migration 019 inseriu `tev_previo` com display_order=7, mas `doenca_vascular` já
ocupava esse número na base (herdado do seed original). Renumera a sequência
completa para eliminar o empate.

Revision ID: 020_fix_display_order
Revises: 019_split_avc_tev
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "020_fix_display_order"
down_revision = "019_split_avc_tev"
branch_labels = None
depends_on = None

SCHEMA = "calculators"
SLUG = "cha2ds2vasc_hasbled"

ORDER = [
    "idade", "sexo", "icc", "hipertensao", "diabetes",
    "avc_ait_previo", "tev_previo", "doenca_vascular",
    "hipertensao_nao_controlada", "funcao_renal_alterada", "funcao_hepatica_alterada",
    "sangramento_previo", "inr_labil", "uso_alcool_drogas",
    "medicamentos_predisponentes_sangramento",
]

# display_order antes desta migration (para o downgrade)
PREVIOUS_ORDER = {
    "idade": 1, "sexo": 2, "icc": 3, "hipertensao": 4, "diabetes": 5,
    "avc_ait_previo": 6, "tev_previo": 7, "doenca_vascular": 7,
    "hipertensao_nao_controlada": 8, "funcao_renal_alterada": 9, "funcao_hepatica_alterada": 10,
    "sangramento_previo": 11, "inr_labil": 12, "uso_alcool_drogas": 13,
    "medicamentos_predisponentes_sangramento": 14,
}


def _apply(conn, calculator_id, mapping: dict) -> None:
    for key, order in mapping.items():
        conn.execute(
            sa.text(f"""
                UPDATE {SCHEMA}.calculator_fields
                SET display_order = :order
                WHERE calculator_id = :cid AND key = :key
            """),
            {"order": order, "cid": calculator_id, "key": key},
        )


def upgrade() -> None:
    conn = op.get_bind()
    calculator_id = conn.execute(
        sa.text(f"SELECT id FROM {SCHEMA}.calculator_definitions WHERE slug = :slug"),
        {"slug": SLUG},
    ).scalar_one_or_none()
    if calculator_id is None:
        return
    _apply(conn, calculator_id, {key: i for i, key in enumerate(ORDER, start=1)})


def downgrade() -> None:
    conn = op.get_bind()
    calculator_id = conn.execute(
        sa.text(f"SELECT id FROM {SCHEMA}.calculator_definitions WHERE slug = :slug"),
        {"slug": SLUG},
    ).scalar_one_or_none()
    if calculator_id is None:
        return
    _apply(conn, calculator_id, PREVIOUS_ORDER)
