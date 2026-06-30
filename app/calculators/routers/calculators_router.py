from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import User
from app.calculators.schemas.calculator_schemas import (
    CalculatorDetailOut,
    CalculatorExecuteRequest,
    CalculatorExecuteResponse,
    CalculatorExecutionHistoryItem,
    CalculatorListItem,
)
from app.calculators.services import calculators_service
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


@router.get("/{slug}/history", response_model=list[CalculatorExecutionHistoryItem])
async def get_calculator_history(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await calculators_service.get_calculator_history(db, slug=slug, user_id=current_user.id)
