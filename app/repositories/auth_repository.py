"""Acesso a dados de autenticação (User/OtpCode/InviteToken), sem regra de negócio
nem commit — quem decide a fronteira da transação é o service (app/services/auth_service.py),
já que vários fluxos encadeiam mais de uma escrita numa única transação."""

import uuid
from datetime import datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AuditLog,
    Conversation,
    Folder,
    Interaction,
    InteractionMedication,
    InteractionResponse,
    InviteToken,
    OtpCode,
    PharmaAlert,
    PubmedValidation,
    User,
    UserPreference,
    UserWeeklyUsage,
)


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


async def apagar_dados_do_usuario(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Remove tudo que pertence ao titular (LGPD art. 18, VI). Sem commit.

    A ORDEM É A DEPENDÊNCIA: as tabelas não têm `ON DELETE CASCADE`, então cada
    filha precisa sair antes da mãe ou o Postgres recusa por chave estrangeira.
    Daí ir das folhas (validações, medicações, alertas) para a raiz (`users`).

    `audit_logs` é a exceção deliberada: NÃO é apagado, só tem o `user_id`
    anulado. É registro de auditoria — apagá-lo destruiria a prova de que as
    ações aconteceram, e a lei pede remover o dado pessoal, não a trilha.

    Estava inline no endpoint `DELETE /auth/me`, misturado com validação de
    entrada. Aqui em cima fica testável sem HTTP e reutilizável por um eventual
    fluxo administrativo.
    """
    conv_ids = list(await db.scalars(select(Conversation.id).where(Conversation.user_id == user_id)))

    if conv_ids:
        inter_ids = list(
            await db.scalars(select(Interaction.id).where(Interaction.conversation_id.in_(conv_ids)))
        )
        if inter_ids:
            for tabela in (PubmedValidation, InteractionMedication, PharmaAlert, InteractionResponse):
                await db.execute(sql_delete(tabela).where(tabela.interaction_id.in_(inter_ids)))
        await db.execute(sql_delete(Interaction).where(Interaction.conversation_id.in_(conv_ids)))

    await db.execute(sql_delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(sql_delete(Folder).where(Folder.user_id == user_id))
    await db.execute(sql_delete(UserPreference).where(UserPreference.user_id == user_id))
    await db.execute(sql_delete(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user_id))
    await db.execute(update(AuditLog).where(AuditLog.user_id == user_id).values(user_id=None))
    await db.execute(sql_delete(User).where(User.id == user_id))
