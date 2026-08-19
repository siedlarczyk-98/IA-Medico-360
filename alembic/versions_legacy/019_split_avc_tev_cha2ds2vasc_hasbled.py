"""Split avc_avc_tev_previo into avc_ait_previo + tev_previo on cha2ds2vasc_hasbled

O critério "S" do HAS-BLED (Pisters et al.) é especificamente AVC — um paciente com
apenas TEV (tromboembolismo venoso) prévio, sem AVC, não deveria somar ponto no
HAS-BLED, só no CHA2DS2-VASc. O campo único anterior misturava os dois eventos e
inflava o HAS-BLED indevidamente nesse caso. Ver
app/calculators/formulas/cardiologia/cha2ds2vasc_hasbled.py.

Revision ID: 019_split_avc_tev
Revises: 018_standardize_timestamps
Create Date: 2026-08-18
"""
import uuid

import sqlalchemy as sa

from alembic import op

revision = "019_split_avc_tev"
down_revision = "018_standardize_timestamps"
branch_labels = None
depends_on = None

SCHEMA = "calculators"
SLUG = "cha2ds2vasc_hasbled"
OLD_KEY = "avc_avc_tev_previo"
NEW_KEY_AVC = "avc_ait_previo"
NEW_KEY_TEV = "tev_previo"


def upgrade() -> None:
    conn = op.get_bind()

    calculator_id = conn.execute(
        sa.text(f"SELECT id FROM {SCHEMA}.calculator_definitions WHERE slug = :slug"),
        {"slug": SLUG},
    ).scalar_one_or_none()
    if calculator_id is None:
        return

    # Renomeia o campo existente para AVC/AIT (mantém os valores já respondidos pelos usuários).
    conn.execute(
        sa.text(f"""
            UPDATE {SCHEMA}.calculator_fields
            SET key = :new_key, label = 'AVC / AIT prévio'
            WHERE calculator_id = :cid AND key = :old_key
        """),
        {"new_key": NEW_KEY_AVC, "old_key": OLD_KEY, "cid": calculator_id},
    )

    # Adiciona o novo campo de TEV, se ainda não existir.
    exists = conn.execute(
        sa.text(f"""
            SELECT 1 FROM {SCHEMA}.calculator_fields WHERE calculator_id = :cid AND key = :key
        """),
        {"cid": calculator_id, "key": NEW_KEY_TEV},
    ).scalar_one_or_none()
    if exists is None:
        conn.execute(
            sa.text(f"""
                INSERT INTO {SCHEMA}.calculator_fields
                    (id, calculator_id, key, label, field_type, unit, required,
                     min_value, max_value, options, display_order, created_at, updated_at)
                VALUES
                    (:id, :cid, :key, 'Tromboembolismo venoso prévio', 'boolean', NULL, false,
                     NULL, NULL, NULL, 7, now(), now())
            """),
            {"id": str(uuid.uuid4()), "cid": calculator_id, "key": NEW_KEY_TEV},
        )


def downgrade() -> None:
    conn = op.get_bind()

    calculator_id = conn.execute(
        sa.text(f"SELECT id FROM {SCHEMA}.calculator_definitions WHERE slug = :slug"),
        {"slug": SLUG},
    ).scalar_one_or_none()
    if calculator_id is None:
        return

    conn.execute(
        sa.text(f"""
            DELETE FROM {SCHEMA}.calculator_fields WHERE calculator_id = :cid AND key = :key
        """),
        {"cid": calculator_id, "key": NEW_KEY_TEV},
    )
    conn.execute(
        sa.text(f"""
            UPDATE {SCHEMA}.calculator_fields
            SET key = :old_key, label = 'AVC / AIT / tromboembolismo venoso prévio'
            WHERE calculator_id = :cid AND key = :new_key
        """),
        {"old_key": OLD_KEY, "new_key": NEW_KEY_AVC, "cid": calculator_id},
    )
