"""
Seed da calculadora de Cockcroft-Gault (clearance de creatinina estimado).
Referência: Cockcroft DW, Gault MH. Nephron. 1976;16(1):31-41.
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
        result = await db.execute(select(Specialty).where(Specialty.slug == "nefrologia"))
        specialty = result.scalar_one_or_none()
        if specialty is None:
            specialty = Specialty(name="Nefrologia", slug="nefrologia")
            db.add(specialty)
            await db.flush()

        result = await db.execute(
            select(CalculatorDefinition).where(CalculatorDefinition.slug == "cockcroft_gault")
        )
        definition = result.scalar_one_or_none()
        if definition is not None:
            print("Calculadora 'cockcroft_gault' já existe — nada a fazer.")
            return

        definition = CalculatorDefinition(
            specialty_id=specialty.id,
            slug="cockcroft_gault",
            name="Clearance de Creatinina (Cockcroft-Gault)",
            description=(
                "Estimativa de clearance de creatinina para ajuste de dose em função renal, "
                "com opção de peso real, ideal ou ajustado."
            ),
            engine_type="formula",
            status="active",
        )
        db.add(definition)
        await db.flush()
        cid = definition.id

        fields = [
            _field(cid, "idade", "Idade", "integer", 1, required=True, unit="anos", min_value=18, max_value=120),
            _field(cid, "peso_kg", "Peso", "number", 2, required=True, unit="kg", min_value=20, max_value=300),
            _field(cid, "altura_cm", "Altura", "number", 3, required=True, unit="cm", min_value=100, max_value=250),
            _field(cid, "sexo", "Sexo biológico", "select", 4, required=True, options=[
                {"value": "F", "label": "Feminino"}, {"value": "M", "label": "Masculino"},
            ]),
            _field(cid, "creatinina_mgdl", "Creatinina sérica", "number", 5, required=True, unit="mg/dL", min_value=0.1, max_value=20),
            _field(cid, "tipo_peso", "Tipo de peso usado", "select", 6, required=True, options=[
                {"value": "real", "label": "Peso real"},
                {"value": "ideal", "label": "Peso ideal"},
                {"value": "ajustado", "label": "Peso ajustado"},
            ]),
        ]
        db.add_all(fields)

        version = CalculatorVersion(
            calculator_id=cid,
            version_number=1,
            formula_key="cockcroft_gault_v1",
            clinical_reference="Cockcroft DW, Gault MH. Nephron. 1976;16(1):31-41.",
            is_active=True,
        )
        db.add(version)

        await db.commit()
        print("Seed de 'cockcroft_gault' concluído.")


if __name__ == "__main__":
    asyncio.run(main())
