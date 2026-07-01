from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators.engine.calculator_engine import execute_calculator
from app.calculators.repositories import calculators_repository as repo
from app.calculators.schemas.calculator_schemas import (
    CalculatorDetailOut,
    CalculatorExecuteResponse,
    CalculatorExecutionHistoryItem,
    CalculatorFieldOut,
    CalculatorListItem,
)


async def list_calculators(db: AsyncSession, *, specialty: str | None) -> list[CalculatorListItem]:
    definitions = await repo.list_definitions(db, specialty_slug=specialty)
    return [
        CalculatorListItem(
            id=d.id,
            slug=d.slug,
            name=d.name,
            description=d.description,
            specialty_slug=d.specialty.slug,
        )
        for d in definitions
    ]


async def get_calculator_detail(db: AsyncSession, slug: str) -> CalculatorDetailOut:
    definition = await repo.get_definition_by_slug(db, slug)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Calculadora '{slug}' não encontrada")

    fields = sorted(definition.fields, key=lambda f: f.display_order)
    return CalculatorDetailOut(
        id=definition.id,
        slug=definition.slug,
        name=definition.name,
        description=definition.description,
        engine_type=definition.engine_type,
        specialty_slug=definition.specialty.slug,
        fields=[CalculatorFieldOut.model_validate(f) for f in fields],
    )


async def run_calculator(
    db: AsyncSession, *, slug: str, inputs: dict, user_id: UUID, company_id: UUID | None, dry_run: bool = False
) -> CalculatorExecuteResponse:
    execution = await execute_calculator(
        db, slug=slug, inputs=inputs, user_id=user_id, company_id=company_id, dry_run=dry_run
    )
    return CalculatorExecuteResponse.model_validate(execution)


async def get_calculator_history(
    db: AsyncSession, *, slug: str, user_id: UUID
) -> list[CalculatorExecutionHistoryItem]:
    definition = await repo.get_definition_by_slug(db, slug)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Calculadora '{slug}' não encontrada")

    executions = await repo.list_executions(db, calculator_id=definition.id, user_id=user_id)
    return [CalculatorExecutionHistoryItem.model_validate(e) for e in executions]
