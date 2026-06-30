from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import delete as sql_delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter

from app.api.deps import COOKIE_NAME, get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import (
    AuditLog,
    Conversation,
    Folder,
    Interaction,
    InteractionMedication,
    InteractionResponse,
    PharmaAlert,
    PubmedValidation,
    User,
    UserPreference,
    UserWeeklyUsage,
)
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


def _set_session_cookie(response: Response, token: str) -> None:
    """Seta o cookie SSO compartilhado entre apps do mesmo domínio raiz, além do token no body."""
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        domain=settings.cookie_domain or None,
        max_age=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Cadastro público: cria usuário e envia link de acesso por email."""
    settings = get_settings()
    if not settings.allow_public_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cadastro por convite apenas")
    await auth_service.register_and_send_invite(db, body.email)


@router.post("/invite/generate", response_model=InviteGenerateResponse)
@limiter.limit("30/minute")
async def generate_invite(
    request: Request,
    body: InviteGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas admins podem gerar convites")
    invite = await auth_service.generate_invite_token(
        db, current_user.id, body.email, body.expires_hours
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="invite.generate",
            entity_type="invite",
            entity_id=invite.id,
            metadata_={"invited_email": body.email},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    settings = get_settings()
    url = f"{settings.frontend_url}/invite?token={invite.token}"
    return InviteGenerateResponse(
        invite_url=url,
        token=str(invite.token),
        expires_at=invite.expires_at,
    )


@router.post("/invite/accept", response_model=TokenResponse)
@limiter.limit("10/minute")
async def accept_invite(request: Request, response: Response, body: InviteAcceptRequest, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.accept_invite(db, body.token, body.email)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


class EmbedTokenRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or len(v) < 3:
            raise ValueError("Email inválido")
        return v


@router.post("/embed/token", response_model=TokenResponse)
@limiter.limit("5/minute")
async def embed_token(
    request: Request,
    response: Response,
    body: EmbedTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Autenticação para embeds externos (ex: Curseduca). Cria usuário se não existir."""
    # Usa apenas o header Origin (definido pelo browser, não forjável via JS no cliente)
    # e exige correspondência exata contra a allowlist — evita bypass por subdomínio.
    origin = request.headers.get("origin", "")
    settings = get_settings()
    allowed_origins = set(settings.embed_allowed_origins) | {settings.calculadoras_url}
    if origin not in allowed_origins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origem não autorizada para embed")

    user, _ = await auth_service.get_or_create_embed_user(body.email, db)
    token = auth_service.create_access_token(user)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


@router.post("/otp/request", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/15minutes")
async def request_otp(request: Request, body: OTPRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.request_otp(db, body.email)


@router.post("/otp/verify", response_model=TokenResponse)
@limiter.limit("5/minute")
async def verify_otp(request: Request, response: Response, body: OTPVerify, db: AsyncSession = Depends(get_db)):
    user, token = await auth_service.verify_otp(db, body.email, body.code)
    _set_session_cookie(response, token)
    return TokenResponse(access_token=token, onboarding_complete=user.onboarding_complete)


@router.post("/onboarding", response_model=TokenResponse)
async def complete_onboarding(
    body: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    current_user.name = body.name
    current_user.phone_number = f"+55{body.phone_number}"
    current_user.med_status = body.med_status
    current_user.crm = body.crm
    current_user.crm_state = body.crm_state
    current_user.specialty = body.specialty
    current_user.enrollment_date = date_type(body.enrollment_year, 1, 1) if body.enrollment_year else None
    current_user.onboarding_complete = True
    await db.commit()
    await db.refresh(current_user)
    from app.services.auth_service import create_access_token
    token = create_access_token(current_user)
    return TokenResponse(access_token=token, onboarding_complete=True)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    resp = UserResponse.model_validate(current_user)
    resp.intercom_user_hash = auth_service.intercom_user_hash(current_user)
    return resp


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

    user_id = current_user.id

    # Coleta IDs das conversas do usuário
    conv_ids_result = await db.execute(select(Conversation.id).where(Conversation.user_id == user_id))
    conv_ids = [r[0] for r in conv_ids_result.fetchall()]

    if conv_ids:
        # Coleta IDs das interactions dessas conversas
        inter_ids_result = await db.execute(select(Interaction.id).where(Interaction.conversation_id.in_(conv_ids)))
        inter_ids = [r[0] for r in inter_ids_result.fetchall()]

        if inter_ids:
            await db.execute(sql_delete(PubmedValidation).where(PubmedValidation.interaction_id.in_(inter_ids)))
            await db.execute(sql_delete(InteractionMedication).where(InteractionMedication.interaction_id.in_(inter_ids)))
            await db.execute(sql_delete(PharmaAlert).where(PharmaAlert.interaction_id.in_(inter_ids)))
            await db.execute(sql_delete(InteractionResponse).where(InteractionResponse.interaction_id.in_(inter_ids)))

        await db.execute(sql_delete(Interaction).where(Interaction.conversation_id.in_(conv_ids)))

    await db.execute(sql_delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(sql_delete(Folder).where(Folder.user_id == user_id))
    await db.execute(sql_delete(UserPreference).where(UserPreference.user_id == user_id))
    await db.execute(sql_delete(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user_id))
    # Nullifica referências em audit_logs (user_id nullable) antes de remover o user
    await db.execute(update(AuditLog).where(AuditLog.user_id == user_id).values(user_id=None))
    await db.execute(sql_delete(User).where(User.id == user_id))
    await db.commit()
