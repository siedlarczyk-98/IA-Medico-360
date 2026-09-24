"""Acesso a dados de autenticação (User/OtpCode/InviteToken), sem regra de negócio
nem commit — quem decide a fronteira da transação é o service (app/services/auth_service.py),
já que vários fluxos encadeiam mais de uma escrita numa única transação."""

import uuid
from datetime import datetime

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calculators import CalculatorExecution
from app.models.models import (
    AuditLog,
    ConsentLog,
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


async def get_active_otps(db: AsyncSession, email: str, *, now: datetime) -> list[OtpCode]:
    """Todos os códigos ainda válidos do e-mail — normalmente um, às vezes dois.

    Dois acontecem de verdade: dois toques em "enviar código" passam juntos pela
    invalidação (ainda não há o que invalidar) e cada um grava o seu. A primeira
    versão esperava UM (`scalar_one_or_none`) e a verificação estourava em 500
    (item 87 de `docs/pitacos-do-fable-2.md`).

    `FOR UPDATE`: quem verifica o código TRAVA as linhas até o commit. Sem isso,
    cinco palpites errados em paralelo liam todos `failed_attempts = 0`, cada um
    gravava 1, e cinco tentativas contavam como uma — o teto de 5 deixava de ser
    teto para quem disparasse os palpites juntos. `ORDER BY id` dá a mesma ordem
    de trava a todos, para dois verificadores não se travarem em cruz.
    """
    stmt = select(OtpCode).where(
        OtpCode.email == email,
        OtpCode.used == False,  # noqa: E712
        OtpCode.expires_at > now,
    ).order_by(OtpCode.id).with_for_update()
    result = await db.execute(stmt)
    return list(result.scalars())


async def invalidate_unused_otps(db: AsyncSession, email: str) -> None:
    await db.execute(
        update(OtpCode)
        .where(OtpCode.email == email, OtpCode.used == False)  # noqa: E712
        .values(used=True)
    )


async def apagar_dados_do_usuario(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Remove tudo que pertence ao titular (LGPD art. 18, VI). Sem commit.

    A ORDEM É A DEPENDÊNCIA: parte das tabelas não tem `ON DELETE CASCADE`, então
    cada filha precisa sair antes da mãe ou o Postgres recusa por chave
    estrangeira. Daí ir das folhas (validações, medicações, alertas) para a raiz
    (`users`). As que TÊM `ON DELETE` no banco (notícias, favoritos de
    calculadora, embeddings, arquivos, uso semanal) saem sozinhas no último
    `DELETE`. O destino de cada tabela está declarado em
    `data_subject_service.DESTINO_DOS_DADOS`, e um teste exige que toda tabela
    ligada a `users` esteja lá.

    `audit_logs` e `consent_logs` NÃO são apagados: são ANONIMIZADOS. Sai o que
    identifica o titular — `user_id`, IP e user-agent — e fica a prova de que a
    ação e o consentimento aconteceram. A lei pede remover o dado pessoal, não a
    trilha.

    ATÉ 2026-09-21 ISTO FALHAVA para qualquer conta real. Quatro chaves sem
    regra de exclusão ficavam fora desta cascata: `consent_logs.user_id` (todo
    usuário com onboarding), `audit_logs.interaction_id` (todo usuário que já
    perguntou algo), `calculator_executions.user_id` e `invite_tokens.created_by`.
    O teste da época criava só preferência e auditoria, e passava.
    """
    usuario = await db.get(User, user_id)
    email = usuario.email if usuario else None

    inter_ids = list(await db.scalars(select(Interaction.id).where(Interaction.user_id == user_id)))
    conv_ids = list(await db.scalars(select(Conversation.id).where(Conversation.user_id == user_id)))
    if conv_ids:
        # Interação em conversa do titular com `user_id` divergente não deveria
        # existir; se existir, sai junto em vez de travar o `DELETE` da conversa.
        inter_ids += list(
            await db.scalars(
                select(Interaction.id).where(
                    Interaction.conversation_id.in_(conv_ids), Interaction.user_id != user_id
                )
            )
        )

    # Execuções de calculadora guardam entrada clínica digitada pelo titular.
    # Antes das interações: `calculator_executions.interaction_id` aponta para elas.
    await db.execute(sql_delete(CalculatorExecution).where(CalculatorExecution.user_id == user_id))

    if inter_ids:
        # A trilha de auditoria sobrevive, desligada da interação que vai sumir.
        await db.execute(
            update(AuditLog).where(AuditLog.interaction_id.in_(inter_ids)).values(interaction_id=None)
        )
        for tabela in (PubmedValidation, InteractionMedication, PharmaAlert, InteractionResponse):
            await db.execute(sql_delete(tabela).where(tabela.interaction_id.in_(inter_ids)))
        await db.execute(sql_delete(Interaction).where(Interaction.id.in_(inter_ids)))

    await db.execute(sql_delete(Conversation).where(Conversation.user_id == user_id))
    await db.execute(sql_delete(Folder).where(Folder.user_id == user_id))
    await db.execute(sql_delete(UserPreference).where(UserPreference.user_id == user_id))
    await db.execute(sql_delete(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user_id))

    anonimo = {"user_id": None, "ip_address": None, "user_agent": None}
    await db.execute(update(AuditLog).where(AuditLog.user_id == user_id).values(**anonimo))
    await db.execute(update(ConsentLog).where(ConsentLog.user_id == user_id).values(**anonimo))

    # Convites que o titular CRIOU continuam valendo para quem os recebeu; só
    # perdem o autor. Os endereçados AO titular, e os códigos de login dele,
    # guardam o e-mail sem chave estrangeira — saem pelo e-mail.
    await db.execute(update(InviteToken).where(InviteToken.created_by == user_id).values(created_by=None))
    if email:
        await db.execute(sql_delete(InviteToken).where(InviteToken.email == email))
        await db.execute(sql_delete(OtpCode).where(OtpCode.email == email))

    await db.execute(sql_delete(User).where(User.id == user_id))
