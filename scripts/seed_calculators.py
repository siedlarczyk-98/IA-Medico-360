"""Seed inicial do módulo de calculadoras: especialidade + CHA2DS2-VASc."""

import asyncio

from app.core.database import async_session_factory
from app.models.calculators import (
    CalculatorDefinition,
    CalculatorField,
    CalculatorVersion,
    Specialty,
)
from sqlalchemy import select


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Specialty).where(Specialty.slug == "cardiologia"))
        specialty = result.scalar_one_or_none()
        if specialty is None:
            specialty = Specialty(name="Cardiologia", slug="cardiologia")
            db.add(specialty)
            await db.flush()

        result = await db.execute(
            select(CalculatorDefinition).where(CalculatorDefinition.slug == "cha2ds2vasc")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = CalculatorDefinition(
                specialty_id=specialty.id,
                slug="cha2ds2vasc",
                name="CHA2DS2-VASc",
                description="Risco de AVC em fibrilação atrial não valvar.",
                engine_type="formula",
                status="active",
            )
            db.add(definition)
            await db.flush()

            fields = [
                CalculatorField(
                    calculator_id=definition.id,
                    key="faixa_etaria",
                    label="Faixa etária",
                    field_type="select",
                    required=True,
                    options=[
                        {"value": "menor_65", "label": "< 65 anos"},
                        {"value": "65_a_74", "label": "65–74 anos"},
                        {"value": "75_mais", "label": "≥ 75 anos"},
                    ],
                    display_order=1,
                ),
                CalculatorField(
                    calculator_id=definition.id, key="sexo_feminino", label="Sexo feminino",
                    field_type="boolean", required=True, display_order=2,
                ),
                CalculatorField(
                    calculator_id=definition.id, key="icc", label="Insuficiência cardíaca congestiva",
                    field_type="boolean", required=True, display_order=3,
                ),
                CalculatorField(
                    calculator_id=definition.id, key="hipertensao", label="Hipertensão",
                    field_type="boolean", required=True, display_order=4,
                ),
                CalculatorField(
                    calculator_id=definition.id, key="avc_previo", label="AVC/AIT/tromboembolismo prévio",
                    field_type="boolean", required=True, display_order=5,
                ),
                CalculatorField(
                    calculator_id=definition.id, key="doenca_vascular", label="Doença vascular",
                    field_type="boolean", required=True, display_order=6,
                ),
                CalculatorField(
                    calculator_id=definition.id, key="diabetes", label="Diabetes",
                    field_type="boolean", required=True, display_order=7,
                ),
            ]
            db.add_all(fields)

            version = CalculatorVersion(
                calculator_id=definition.id,
                version_number=1,
                formula_key="cha2ds2vasc_v1",
                clinical_reference="ESC Guidelines for AF management",
                is_active=True,
            )
            db.add(version)

        await db.commit()
        print("Seed concluído.")


if __name__ == "__main__":
    asyncio.run(main())
