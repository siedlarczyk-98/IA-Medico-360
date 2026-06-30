from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.calculators import (
    CalculatorDefinition,
    CalculatorExecution,
    CalculatorVersion,
    Specialty,
)


async def list_definitions(db: AsyncSession, *, specialty_slug: str | None = None) -> list[CalculatorDefinition]:
    stmt = (
        select(CalculatorDefinition)
        .where(CalculatorDefinition.status == "active")
        .options(selectinload(CalculatorDefinition.specialty))
        .order_by(CalculatorDefinition.name)
    )
    if specialty_slug:
        stmt = stmt.join(Specialty).where(Specialty.slug == specialty_slug)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_definition_by_slug(db: AsyncSession, slug: str) -> CalculatorDefinition | None:
    stmt = (
        select(CalculatorDefinition)
        .where(CalculatorDefinition.slug == slug, CalculatorDefinition.status == "active")
        .options(
            selectinload(CalculatorDefinition.specialty),
            selectinload(CalculatorDefinition.fields),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_version(db: AsyncSession, calculator_id: UUID) -> CalculatorVersion | None:
    stmt = select(CalculatorVersion).where(
        CalculatorVersion.calculator_id == calculator_id,
        CalculatorVersion.is_active.is_(True),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_executions(
    db: AsyncSession, *, calculator_id: UUID, user_id: UUID, limit: int = 50
) -> list[CalculatorExecution]:
    stmt = (
        select(CalculatorExecution)
        .where(
            CalculatorExecution.calculator_id == calculator_id,
            CalculatorExecution.user_id == user_id,
        )
        .order_by(CalculatorExecution.createdat.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
