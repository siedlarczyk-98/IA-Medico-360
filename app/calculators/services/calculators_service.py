from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.calculators import cache
from app.calculators.engine.calculator_engine import execute_calculator
from app.calculators.repositories import calculators_repository as repo
from app.calculators.schemas.calculator_schemas import (
    CalculatorDetailOut,
    CalculatorExecuteResponse,
    CalculatorExecutionHistoryItem,
    CalculatorFieldOut,
    CalculatorListItem,
)


async def _catalog_items(db: AsyncSession, specialty: str | None) -> list[CalculatorListItem]:
    """Parte do catálogo que não depende do usuário (logo, cacheável)."""
    cache_key = f"list:{specialty or '*'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    definitions = await repo.list_definitions(db, specialty_slug=specialty)
    items = [
        CalculatorListItem(
            id=d.id,
            slug=d.slug,
            name=d.name,
            description=d.description,
            specialty_slug=d.specialty.slug,
        )
        for d in definitions
    ]
    return cache.set_(cache_key, items)


async def list_calculators(db: AsyncSession, *, specialty: str | None, user_id: UUID) -> list[CalculatorListItem]:
    items = await _catalog_items(db, specialty)
    favorite_ids = await repo.list_favorite_calculator_ids(db, user_id=user_id)
    # Copia: os itens cacheados são compartilhados entre usuários e `is_favorite`
    # é por usuário — mutar o objeto do cache vazaria favoritos entre contas.
    return [item.model_copy(update={"is_favorite": item.id in favorite_ids}) for item in items]


async def get_calculator_detail(db: AsyncSession, slug: str) -> CalculatorDetailOut:
    cache_key = f"detail:{slug}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    definition = await repo.get_definition_or_404(db, slug)

    fields = sorted(definition.fields, key=lambda f: f.display_order)
    detail = CalculatorDetailOut(
        id=definition.id,
        slug=definition.slug,
        name=definition.name,
        description=definition.description,
        engine_type=definition.engine_type,
        specialty_slug=definition.specialty.slug,
        fields=[CalculatorFieldOut.model_validate(f) for f in fields],
    )
    return cache.set_(cache_key, detail)


async def set_favorite(db: AsyncSession, *, slug: str, user_id: UUID, favorite: bool) -> None:
    definition = await repo.get_definition_or_404(db, slug)

    if favorite:
        await repo.add_favorite(db, user_id=user_id, calculator_id=definition.id)
    else:
        await repo.remove_favorite(db, user_id=user_id, calculator_id=definition.id)
    await db.commit()


async def run_calculator(
    db: AsyncSession, *, slug: str, inputs: dict, user_id: UUID, company_id: UUID | None, dry_run: bool = False
) -> CalculatorExecuteResponse:
    execution = await execute_calculator(
        db, slug=slug, inputs=inputs, user_id=user_id, company_id=company_id, dry_run=dry_run
    )
    return CalculatorExecuteResponse.model_validate(execution)


async def get_calculator_history(
    db: AsyncSession, *, slug: str, user_id: UUID, limit: int = 50, offset: int = 0
) -> list[CalculatorExecutionHistoryItem]:
    definition = await repo.get_definition_or_404(db, slug)

    executions = await repo.list_executions(
        db, calculator_id=definition.id, user_id=user_id, limit=limit, offset=offset
    )
    return [CalculatorExecutionHistoryItem.model_validate(e) for e in executions]
