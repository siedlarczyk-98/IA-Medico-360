"""
Seed da calculadora CURB-65 (gravidade de pneumonia adquirida na comunidade).
Referência: Lim WS et al., Thorax. 2003;58(5):377-82.
"""

import asyncio

from app.core.database import async_session_factory
from app.models.calculators import (
    CalculatorDefinition,
    CalculatorField,
    CalculatorVersion,
    Specialty,
)
from sqlalchemy import select


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
        result = await db.execute(select(Specialty).where(Specialty.slug == "infectologia"))
        specialty = result.scalar_one_or_none()
        if specialty is None:
            specialty = Specialty(name="Infectologia", slug="infectologia")
            db.add(specialty)
            await db.flush()

        result = await db.execute(
            select(CalculatorDefinition).where(CalculatorDefinition.slug == "curb65")
        )
        definition = result.scalar_one_or_none()
        if definition is not None:
            print("Calculadora 'curb65' já existe — nada a fazer.")
            return

        definition = CalculatorDefinition(
            specialty_id=specialty.id,
            slug="curb65",
            name="CURB-65",
            description="Gravidade de pneumonia adquirida na comunidade e orientação de internação.",
            engine_type="formula",
            status="active",
        )
        db.add(definition)
        await db.flush()
        cid = definition.id

        fields = [
            _field(cid, "confusao_mental", "Confusão mental (nova)", "boolean", 1, required=False),
            _field(cid, "ureia_mgdl", "Ureia sérica", "number", 2, required=True, unit="mg/dL", min_value=5, max_value=300),
            _field(cid, "fr_irpm", "Frequência respiratória", "integer", 3, required=True, unit="irpm", min_value=5, max_value=60),
            _field(cid, "pas_mmhg", "Pressão arterial sistólica", "integer", 4, required=True, unit="mmHg", min_value=40, max_value=300),
            _field(cid, "pad_mmhg", "Pressão arterial diastólica", "integer", 5, required=True, unit="mmHg", min_value=20, max_value=200),
            _field(cid, "idade", "Idade", "integer", 6, required=True, unit="anos", min_value=0, max_value=120),
        ]
        db.add_all(fields)

        version = CalculatorVersion(
            calculator_id=cid,
            version_number=1,
            formula_key="curb65_v1",
            clinical_reference="Lim WS et al., Thorax. 2003;58(5):377-82.",
            is_active=True,
        )
        db.add(version)

        await db.commit()
        print("Seed de 'curb65' concluído.")


if __name__ == "__main__":
    asyncio.run(main())
