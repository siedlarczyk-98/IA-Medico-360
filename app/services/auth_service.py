import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
import jwt as pyjwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import InviteToken, OtpCode, User
from app.services import email_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user: "User") -> str:
    from app.models.models import User as UserModel  # avoid circular at module level
    settings = get_settings()
    expire = _utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": expire,
    }
    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def generate_invite_token(
    db: AsyncSession,
    created_by: uuid.UUID,
    email: str | None = None,
    expires_hours: int | None = None,
) -> InviteToken:
    settings = get_settings()
    hours = expires_hours if expires_hours is not None else settings.invite_token_expire_hours
    invite = InviteToken(
        token=uuid.uuid4(),
        email=email,
        created_by=created_by,
        expires_at=_utcnow() + timedelta(hours=hours),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def _get_valid_invite(db: AsyncSession, token_str: str) -> InviteToken:
    try:
        token_uuid = uuid.UUID(token_str)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token de convite inválido")

    result = await db.execute(
        select(InviteToken).where(InviteToken.token == token_uuid)
    )
    invite = result.scalar_one_or_none()
    if not invite or invite.used or invite.expires_at < _utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link de convite inválido ou expirado")
    return invite


async def accept_invite(
    db: AsyncSession, token_str: str, email: str | None = None
) -> tuple[User, str]:
    invite = await _get_valid_invite(db, token_str)

    resolved_email = invite.email or email
    if not resolved_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email é obrigatório")

    result = await db.execute(select(User).where(User.email == resolved_email))
    user = result.scalar_one_or_none()

    # Open invites (no pre-bound email) must never grant access to existing accounts —
    # that would allow any token holder to take over arbitrary accounts by supplying their email.
    if user is not None and invite.email is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Email já cadastrado. Faça login pelo código OTP.",
        )

    if not user:
        user = User(email=resolved_email, role="beta_user", status=True, onboarding_complete=False)
        db.add(user)

    invite.used = True
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user)
    return user, token


async def register_and_send_invite(db: AsyncSession, email: str) -> None:
    """Auto-cadastro: cria usuário (se não existir) e envia link de convite por email."""
    settings = get_settings()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=email, role="beta_user", status=True, onboarding_complete=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    invite = InviteToken(
        token=uuid.uuid4(),
        email=email,
        expires_at=_utcnow() + timedelta(hours=settings.invite_token_expire_hours),
    )
    db.add(invite)
    await db.commit()

    invite_url = f"{settings.frontend_url}/invite?token={invite.token}"
    await email_service.send_invite(email, invite_url)


async def request_otp(db: AsyncSession, email: str) -> None:
    result = await db.execute(select(User).where(User.email == email, User.status == True))
    user = result.scalar_one_or_none()
    if not user:
        return  # silencioso — não revelar se email existe

    # Invalidate existing unused OTPs for this email
    await db.execute(
        update(OtpCode)
        .where(OtpCode.email == email, OtpCode.used == False)
        .values(used=True)
    )

    settings = get_settings()
    code = str(secrets.randbelow(900000) + 100000)
    otp = OtpCode(
        email=email,
        code=code,
        expires_at=_utcnow() + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(otp)
    await db.commit()

    await email_service.send_otp(email, code)


_OTP_MAX_ATTEMPTS = 5


async def verify_otp(db: AsyncSession, email: str, code: str) -> tuple[User, str]:
    now = _utcnow()
    result = await db.execute(
        select(OtpCode).where(
            OtpCode.email == email,
            OtpCode.used == False,
            OtpCode.expires_at > now,
        )
    )
    otp = result.scalar_one_or_none()
    if not otp:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")

    if otp.failed_attempts >= _OTP_MAX_ATTEMPTS:
        otp.used = True
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")

    if otp.code != code:
        otp.failed_attempts += 1
        if otp.failed_attempts >= _OTP_MAX_ATTEMPTS:
            otp.used = True
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido ou expirado")

    otp.used = True

    result = await db.execute(select(User).where(User.email == email, User.status == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")

    await db.commit()

    token = create_access_token(user)
    return user, token
