"""
Seed da calculadora PREVENT avulsa (AHA, Khan et al., Circulation 2024;149(6):430-449).

A mesma equação que o wizard `risco_cv_sbc2025` usa no Step4, exposta como
calculadora própria na lista. O registro aqui existe para a PREVENT ter card,
especialidade e favoritagem como as demais; o cálculo em si NÃO passa pelo motor
genérico de calculadoras — a tela chama `POST /api/v1/prevent/calculate` direto
(ver `calculadoras-app/src/calculators/prevent/`). Por isso não há
`CalculatorVersion` com `formula_key` executável, só a definição e os campos.
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
            select(CalculatorDefinition).where(CalculatorDefinition.slug == "prevent_aha2024")
        )
        definition = result.scalar_one_or_none()
        if definition is not None:
            print("Calculadora 'prevent_aha2024' já existe — nada a fazer.")
            return

        definition = CalculatorDefinition(
            specialty_id=specialty.id,
            slug="prevent_aha2024",
            name="PREVENT (AHA 2024)",
            description=(
                "Risco de doença cardiovascular total, aterosclerótica e insuficiência "
                "cardíaca em 10 e 30 anos. Modelo base da American Heart Association."
            ),
            engine_type="formula",
            status="active",
        )
        db.add(definition)
        await db.flush()
        cid = definition.id

        # As faixas replicam as do modelo base da AHA. Fora delas o backend
        # invalida desfecho a desfecho e devolve o aviso correspondente — os
        # limites aqui servem ao card/lista, não são a validação de verdade.
        fields = [
            _field(cid, "sexo", "Sexo biológico", "select", 1, required=True, options=[
                {"value": "F", "label": "Feminino"}, {"value": "M", "label": "Masculino"},
            ]),
            _field(cid, "idade", "Idade", "integer", 2, required=True, unit="anos", min_value=30, max_value=79),
            _field(cid, "ct_mgdl", "Colesterol total", "number", 3, required=True, unit="mg/dL", min_value=130, max_value=320),
            _field(cid, "hdl_mgdl", "HDL-c", "number", 4, required=True, unit="mg/dL", min_value=20, max_value=100),
            _field(cid, "sbp_mmhg", "Pressão arterial sistólica", "number", 5, required=True, unit="mmHg", min_value=90, max_value=180),
            _field(cid, "bmi", "IMC", "number", 6, required=True, unit="kg/m²", min_value=18.5, max_value=39.9),
            _field(cid, "egfr", "TFGe (eGFR)", "number", 7, required=True, unit="mL/min/1,73m²", min_value=15, max_value=140),
            _field(cid, "diabetes", "Diabetes mellitus", "boolean", 8, required=False),
            _field(cid, "fumante", "Tabagismo atual", "boolean", 9, required=False),
            _field(cid, "antihtn_use", "Uso de anti-hipertensivo", "boolean", 10, required=False),
            _field(cid, "statin_use", "Uso de estatina", "boolean", 11, required=False),
        ]
        db.add_all(fields)

        version = CalculatorVersion(
            calculator_id=cid,
            version_number=1,
            formula_key="prevent_aha2024_v1",
            clinical_reference=(
                "Khan SS, Matsushita K, Sang Y, et al. Development and Validation of the "
                "American Heart Association PREVENT Equations. Circulation. "
                "2024;149(6):430-449 (Tabelas S12A/S12F, modelo base)."
            ),
            is_active=True,
        )
        db.add(version)

        await db.commit()
        print("Seed de 'prevent_aha2024' concluído.")


if __name__ == "__main__":
    asyncio.run(main())
