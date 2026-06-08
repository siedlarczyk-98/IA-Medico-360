from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import User
from app.schemas.auth import (
    DeleteAccountRequest,
    InviteAcceptRequest,
    InviteGenerateRequest,
    InviteGenerateResponse,
    OnboardingRequest,
    OTPRequest,
    OTPVerify,
    RegisterRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_204_NO_CONTENT)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Cadastro público: cria usuário e envia link de acesso por email."""
    settings = get_settings()
    if not settings.allow_public_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cadastro por convite apenas")
    await auth_service.register_and_send_invite(db, body.email)


@router.post("/invite/generate", response_model=InviteGenerateResponse)
async def generate_invite(
    body: InviteGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas admins podem gerar convites")
    invite = await auth_service.generate_invite_token(
        db, current_user.id, body.email, body.expires_hours
    )
    settings = get_settings()
    url = f"{settings.frontend_url}/invite?token={invite.token}"
    return InviteGenerateResponse(
        invite_url=url,
        token=str(invite.token),
        expires_at=invite.expires_at,
    )


@router.post("/invite/accept", response_model=TokenResponse)
async def accept_invite(body: InviteAcceptRequest, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.accept_invite(db, body.token, body.email)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


@router.post("/otp/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_otp(body: OTPRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.request_otp(db, body.email)


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(body: OTPVerify, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.verify_otp(db, body.email, body.code)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


@router.post("/onboarding", response_model=TokenResponse)
async def complete_onboarding(
    body: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.name = body.name
    current_user.phone_number = f"+55{body.phone_number}"
    current_user.med_status = body.med_status
    current_user.crm = body.crm
    current_user.crm_state = body.crm_state
    current_user.enrollment_date = body.enrollment_date
    current_user.onboarding_complete = True
    await db.commit()
    await db.refresh(current_user)
    from app.services.auth_service import create_access_token
    token = create_access_token(current_user)
    return TokenResponse(access_token=token, onboarding_complete=True)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=TokenResponse)
async def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.email and body.email != current_user.email:
        result = await db.execute(select(User).where(User.email == body.email))
        if result.scalar_one_or_none():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email já está em uso")
        current_user.email = body.email
    if body.name is not None:
        current_user.name = body.name
    await db.commit()
    await db.refresh(current_user)
    from app.services.auth_service import create_access_token
    token = create_access_token(current_user)
    return TokenResponse(access_token=token, onboarding_complete=current_user.onboarding_complete)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete o onboarding antes de excluir a conta")
    if not body.confirm_name or body.confirm_name != current_user.name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nome de confirmação não confere")
    await db.delete(current_user)
    await db.commit()
