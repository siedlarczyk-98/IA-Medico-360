import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.landing_pages import (
    AccountingAnswer,
    AccountingPainSelection,
    CalculatorSelection,
    FinanceAnswer,
    LandingPage,
    Submission,
)
from app.models.models import User
from app.schemas.landing_pages import (
    AccountingSubmissionRequest,
    AlreadySubmittedResponse,
    CalculatorSubmissionRequest,
    FinanceSubmissionRequest,
    SubmissionResponse,
)

router = APIRouter(prefix="/landing-pages", tags=["landing-pages"])

# Slugs vem do catalogo (migration 000b). Validar contra essa lista antes de
# consultar evita 500 generico quando o path param e arbitrario (GET /check
# recebe slug do usuario, diferente dos POSTs de submit que usam slug fixo).
ALLOWED_SLUGS = {"finance", "accounting", "benefits", "calculators"}


async def _get_landing_page_id(db: AsyncSession, slug: str) -> uuid.UUID:
    result = await db.execute(select(LandingPage.id).where(LandingPage.slug == slug))
    landing_page_id = result.scalar_one_or_none()
    if landing_page_id is None:
        # So acontece se o seed do catalogo (migration 000b) nao rodou nesse banco.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"LP '{slug}' não cadastrada")
    return landing_page_id


async def _already_submitted(db: AsyncSession, slug: str, email: str | None) -> bool:
    """Bloqueio por email: so faz sentido quando o email veio da URL (embed do
    fornecedor) — sem email nao ha como identificar reenvio, e a submissao
    segue permitida (mesmo comportamento de antes)."""
    if not email:
        return False
    result = await db.execute(
        select(Submission.id)
        .join(LandingPage, LandingPage.id == Submission.landing_page_id)
        .where(LandingPage.slug == slug, Submission.email == email)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


@router.get("/{slug}/check", response_model=AlreadySubmittedResponse)
@limiter.limit("60/minute")
async def check_already_submitted(
    request: Request,
    slug: str,
    email: str = "",
    db: AsyncSession = Depends(get_db),
):
    if slug not in ALLOWED_SLUGS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"LP '{slug}' não encontrada")
    return AlreadySubmittedResponse(already_submitted=await _already_submitted(db, slug, email or None))


@router.post("/finance/submit", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def submit_finance_interest(
    request: Request,
    body: FinanceSubmissionRequest,
    db: AsyncSession = Depends(get_db),
):
    if await _already_submitted(db, "finance", body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Você já registrou seu interesse nesta LP")

    landing_page_id = await _get_landing_page_id(db, "finance")

    submission = Submission(
        landing_page_id=landing_page_id,
        name=body.name,
        email=body.email,
        email_missing=body.email_missing,
    )
    db.add(submission)
    await db.flush()

    db.add(
        FinanceAnswer(
            submission_id=submission.id,
            career_stage=body.career_stage,
            main_pain_point=body.main_pain_point,
        )
    )
    await db.commit()

    return SubmissionResponse()


@router.post("/accounting/submit", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def submit_accounting_interest(
    request: Request,
    body: AccountingSubmissionRequest,
    db: AsyncSession = Depends(get_db),
):
    if await _already_submitted(db, "accounting", body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Você já registrou seu interesse nesta LP")

    landing_page_id = await _get_landing_page_id(db, "accounting")

    submission = Submission(
        landing_page_id=landing_page_id,
        name=body.name,
        email=body.email,
        email_missing=body.email_missing,
    )
    db.add(submission)
    await db.flush()

    db.add(
        AccountingAnswer(
            submission_id=submission.id,
            career_stage=body.career_stage,
            income_method=body.income_method,
            accountant_status=body.accountant_status,
            revenue_range=body.revenue_range,
            willingness_to_pay=body.willingness_to_pay,
        )
    )
    db.add_all(
        AccountingPainSelection(submission_id=submission.id, option=option)
        for option in body.pain_points
    )
    await db.commit()

    return SubmissionResponse()


@router.post("/calculators/submit", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def submit_calculators_interest(
    request: Request,
    body: CalculatorSubmissionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Solicitação feita de dentro do módulo de calculadoras (médico logado) —
    diferente das outras LPs, aqui a identidade vem da conta, não do body."""
    existing = await db.execute(
        select(Submission.id)
        .join(LandingPage, LandingPage.id == Submission.landing_page_id)
        .where(LandingPage.slug == "calculators", Submission.user_id == current_user.id)
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você já registrou esse pedido")

    landing_page_id = await _get_landing_page_id(db, "calculators")

    submission = Submission(
        landing_page_id=landing_page_id,
        user_id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        notify_on_availability=body.notify_on_availability,
    )
    db.add(submission)
    await db.flush()

    db.add_all(
        CalculatorSelection(submission_id=submission.id, option=option)
        for option in body.calculators
    )
    await db.commit()

    return SubmissionResponse()
