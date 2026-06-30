from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import User
from app.calculators.repositories import calculators_repository
from app.calculators.schemas.calculator_schemas import (
    CalculatorDetailOut,
    CalculatorExecuteRequest,
    CalculatorExecuteResponse,
    CalculatorExecutionHistoryItem,
    CalculatorExtractRequest,
    CalculatorExtractResponse,
    CalculatorListItem,
)
from app.calculators.services import calculators_service, extraction_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/calculators", tags=["calculators"])


@router.get("", response_model=list[CalculatorListItem])
@limiter.limit("60/minute")
async def list_calculators(
    request: Request,
    specialty: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await calculators_service.list_calculators(db, specialty=specialty)


@router.get("/{slug}", response_model=CalculatorDetailOut)
async def get_calculator(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await calculators_service.get_calculator_detail(db, slug)


@router.post("/{slug}/execute", response_model=CalculatorExecuteResponse)
@limiter.limit("60/minute")
async def execute_calculator(
    request: Request,
    slug: str,
    body: CalculatorExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await calculators_service.run_calculator(
        db,
        slug=slug,
        inputs=body.inputs,
        user_id=current_user.id,
        company_id=current_user.company_id,
    )


@router.post("/{slug}/extract", response_model=CalculatorExtractResponse)
@limiter.limit("30/minute")
async def extract_calculator_fields(
    request: Request,
    slug: str,
    body: CalculatorExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    definition = await calculators_repository.get_definition_by_slug(db, slug)
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Calculadora '{slug}' não encontrada")

    suggested_inputs, fields_extracted = await extraction_service.extract_calculator_inputs(
        db,
        fields=definition.fields,
        text=body.text,
        user_id=current_user.id,
    )
    return CalculatorExtractResponse(
        suggested_inputs=suggested_inputs,
        fields_extracted=fields_extracted,
        interaction_id=None,
    )


@router.get("/{slug}/history", response_model=list[CalculatorExecutionHistoryItem])
async def get_calculator_history(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await calculators_service.get_calculator_history(db, slug=slug, user_id=current_user.id)
