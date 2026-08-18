from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.calculators import (
    CalculatorDefinition,
    CalculatorExecution,
    CalculatorFavorite,
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


async def get_definition_or_404(db: AsyncSession, slug: str) -> CalculatorDefinition:
    definition = await get_definition_by_slug(db, slug)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Calculadora '{slug}' não encontrada")
    return definition


async def get_active_version(db: AsyncSession, calculator_id: UUID) -> CalculatorVersion | None:
    stmt = (
        select(CalculatorVersion)
        .where(
            CalculatorVersion.calculator_id == calculator_id,
            CalculatorVersion.is_active.is_(True),
        )
        .order_by(CalculatorVersion.version_number.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_favorite_calculator_ids(db: AsyncSession, *, user_id: UUID) -> set[UUID]:
    stmt = select(CalculatorFavorite.calculator_id).where(CalculatorFavorite.user_id == user_id)
    result = await db.execute(stmt)
    return set(result.scalars().all())


async def add_favorite(db: AsyncSession, *, user_id: UUID, calculator_id: UUID) -> None:
    stmt = (
        pg_insert(CalculatorFavorite)
        .values(user_id=user_id, calculator_id=calculator_id)
        .on_conflict_do_nothing(constraint="uq_calculator_favorites_user_calculator")
    )
    await db.execute(stmt)


async def remove_favorite(db: AsyncSession, *, user_id: UUID, calculator_id: UUID) -> None:
    stmt = delete(CalculatorFavorite).where(
        CalculatorFavorite.user_id == user_id,
        CalculatorFavorite.calculator_id == calculator_id,
    )
    await db.execute(stmt)


async def list_executions(
    db: AsyncSession, *, calculator_id: UUID, user_id: UUID, limit: int = 50, offset: int = 0
) -> list[CalculatorExecution]:
    stmt = (
        select(CalculatorExecution)
        .where(
            CalculatorExecution.calculator_id == calculator_id,
            CalculatorExecution.user_id == user_id,
        )
        .order_by(CalculatorExecution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
