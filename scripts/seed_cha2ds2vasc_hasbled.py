"""
Seed da calculadora combinada CHA2DS2-VASc + HAS-BLED.
Referências: ESC Guidelines for AF management (CHA2DS2-VASc);
Pisters et al., Chest. 2010;138(5):1093-100 (HAS-BLED).
"""

import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.calculators import (
    CalculatorDefinition,
    CalculatorField,
    CalculatorVersion,
    Specialty,
)


def _field(calculator_id, key, label, field_type, order, **kwargs):
    return CalculatorField(
        calculator_id=calculator_id,
        key=key,
        label=label,
        field_type=field_type,
        display_order=order,
        **kwargs,
    )


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Specialty).where(Specialty.slug == "cardiologia"))
        specialty = result.scalar_one_or_none()
        if specialty is None:
            specialty = Specialty(name="Cardiologia", slug="cardiologia")
            db.add(specialty)
            await db.flush()

        result = await db.execute(
            select(CalculatorDefinition).where(CalculatorDefinition.slug == "cha2ds2vasc_hasbled")
        )
        definition = result.scalar_one_or_none()
        if definition is not None:
            print("Calculadora 'cha2ds2vasc_hasbled' já existe — nada a fazer.")
            return

        definition = CalculatorDefinition(
            specialty_id=specialty.id,
            slug="cha2ds2vasc_hasbled",
            name="CHA2DS2-VASc + HAS-BLED",
            description=(
                "Risco de AVC (CHA2DS2-VASc) e risco de sangramento (HAS-BLED) em fibrilação "
                "atrial não valvar"
            ),
            engine_type="formula",
            status="active",
        )
        db.add(definition)
        await db.flush()
        cid = definition.id

        fields = [
            _field(cid, "idade", "Idade", "integer", 1, required=True, unit="anos", min_value=18, max_value=120),
            _field(cid, "sexo", "Sexo biológico", "select", 2, required=True, options=[
                {"value": "F", "label": "Feminino"}, {"value": "M", "label": "Masculino"},
            ]),

            # ── CHA2DS2-VASc ──────────────────────────────────────────────
            _field(cid, "icc", "Insuficiência cardíaca", "boolean", 3, required=False),
            _field(cid, "hipertensao", "Hipertensão", "boolean", 4, required=False),
            _field(cid, "diabetes", "Diabetes", "boolean", 5, required=False),
            _field(cid, "avc_ait_previo", "AVC / AIT prévio", "boolean", 6, required=False),
            _field(cid, "tev_previo", "Tromboembolismo venoso prévio", "boolean", 7, required=False),
            _field(cid, "doenca_vascular", "Doença vascular", "boolean", 8, required=False),

            # ── HAS-BLED ──────────────────────────────────────────────────
            _field(cid, "hipertensao_nao_controlada", "Hipertensão não controlada", "boolean", 9, required=False),
            _field(cid, "funcao_renal_alterada", "Função renal alterada", "boolean", 10, required=False),
            _field(cid, "funcao_hepatica_alterada", "Função hepática alterada", "boolean", 11, required=False),
            _field(cid, "sangramento_previo", "Sangramento prévio ou predisposição a sangramento", "boolean", 12, required=False),
            _field(cid, "inr_labil", "INR lábil", "boolean", 13, required=False),
            _field(cid, "uso_alcool_drogas", "Uso de álcool ou drogas", "boolean", 14, required=False),
            _field(cid, "medicamentos_predisponentes_sangramento", "Uso de medicamentos que predispõem a sangramento", "boolean", 15, required=False),
        ]
        db.add_all(fields)

        version = CalculatorVersion(
            calculator_id=cid,
            version_number=1,
            formula_key="cha2ds2vasc_hasbled_v1",
            clinical_reference=(
                "ESC Guidelines for AF management (CHA2DS2-VASc); "
                "Pisters et al., Chest. 2010;138(5):1093-100 (HAS-BLED)."
            ),
            is_active=True,
        )
        db.add(version)

        await db.commit()
        print("Seed de 'cha2ds2vasc_hasbled' concluído.")


if __name__ == "__main__":
    asyncio.run(main())
