"""Acesso a dados de autenticação (User/OtpCode/InviteToken), sem regra de negócio
nem commit — quem decide a fronteira da transação é o service (app/services/auth_service.py),
já que vários fluxos encadeiam mais de uma escrita numa única transação."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import InviteToken, OtpCode, User


async def get_user_by_email(db: AsyncSession, email: str, *, active_only: bool = False) -> User | None:
    stmt = select(User).where(User.email == email)
    if active_only:
        stmt = stmt.where(User.status.is_(True))  # noqa: E712 (comparação SQLAlchemy, não booleana Python)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_invite_by_token(db: AsyncSession, token: uuid.UUID) -> InviteToken | None:
    result = await db.execute(select(InviteToken).where(InviteToken.token == token))
    return result.scalar_one_or_none()


async def get_active_otp(db: AsyncSession, email: str, *, now: datetime) -> OtpCode | None:
    stmt = select(OtpCode).where(
        OtpCode.email == email,
        OtpCode.used == False,  # noqa: E712
        OtpCode.expires_at > now,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def invalidate_unused_otps(db: AsyncSession, email: str) -> None:
    await db.execute(
        update(OtpCode)
        .where(OtpCode.email == email, OtpCode.used == False)  # noqa: E712
        .values(used=True)
    )
