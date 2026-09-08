from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog, User, UserWeeklyUsage

# Teto de gasto semanal por usuário beta, em USD.
#
# Era 1,00, calibrado quando a pergunta mais cara custava ~US$ 0,03 — trinta
# perguntas por semana, folgado para um piloto.
#
# O DATA_OCEAN mudou a escala. Medição da primeira consulta real em produção
# (2026-09-08): US$ 0,647945 — 22× uma pergunta clínica comum. Não é o modelo:
# são os 25,2 GB que a ferramenta processa e os 147 mil tokens que ela injeta
# no contexto do lado da Maritaca.
#
# Com o teto de 1,00, cabia UMA VEZ E MEIA por semana. Na segunda consulta o
# médico batia o limite e perdia TODOS os modos — inclusive a busca rápida, que
# custa centavos. Um limite que derruba a plataforma inteira por causa de duas
# perguntas não protege orçamento: impede o uso.
#
# 5,00 comporta ~7 consultas Data Ocean, ou ~170 perguntas clínicas comuns, ou
# qualquer mistura. Com 18 usuários, o pior caso absoluto é US$ 90/semana — e
# ninguém chega perto, porque o consumo real medido é de dezenas de interações
# por mês, não por semana.
#
# QUANDO REVISAR: se o custo médio por interação subir de novo (um modo novo
# mais caro, ou a Maritaca reajustar), ou quando a base sair da escala de
# piloto. `vigilancia_service.medir_custo` mostra o gasto por período.
BETA_WEEKLY_LIMIT = Decimal("5.00")
BETA_ROLE = "beta_user"


def add_interaction_audit(
    db: AsyncSession,
    *,
    user_id,
    interaction_id,
    action: str,
    metadata: dict,
) -> AuditLog:
    """
    Cria e enfileira um AuditLog padronizado para uma interação.
    Centraliza o wrapper repetido em Orquestrador e Agregador — o conteúdo
    de `metadata` continua específico de cada fluxo.
    """
    audit = AuditLog(
        user_id=user_id,
        interaction_id=interaction_id,
        action=action,
        entity_type="interaction",
        entity_id=interaction_id,
        metadata_=metadata,
    )
    db.add(audit)
    return audit


async def _get_or_create_usage(db: AsyncSession, user_id) -> UserWeeklyUsage:
    # Cache within the same db session to avoid double-SELECT per request
    cache_key = f"_usage_{user_id}"
    if cache_key in db.info:
        return db.info[cache_key]
    result = await db.execute(select(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user_id))
    usage = result.scalar_one_or_none()
    if usage is None:
        usage = UserWeeklyUsage(
            user_id=user_id,
            week_start=datetime.now(UTC),
            total_cost_usd=Decimal("0"),
        )
        db.add(usage)
        await db.flush()
    db.info[cache_key] = usage
    return usage


async def _reset_if_expired(db: AsyncSession, usage: UserWeeklyUsage) -> None:
    now = datetime.now(UTC)
    week_end = usage.week_start + timedelta(days=7)
    if now >= week_end:
        usage.week_start = now
        usage.total_cost_usd = Decimal("0")
        await db.flush()


async def check_limit(db: AsyncSession, user: User) -> None:
    if user.role != BETA_ROLE:
        return
    usage = await _get_or_create_usage(db, user.id)
    await _reset_if_expired(db, usage)
    if usage.total_cost_usd >= BETA_WEEKLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite semanal de uso atingido. Seu limite será reiniciado em 7 dias a partir da sua primeira interação.",
        )


async def record_cost(db: AsyncSession, user_id, cost_usd: Decimal) -> None:
    if cost_usd <= Decimal("0"):
        return
    usage = await _get_or_create_usage(db, user_id)
    await _reset_if_expired(db, usage)
    usage.total_cost_usd += cost_usd
    await db.flush()


async def get_usage_info(db: AsyncSession, user: User) -> dict:
    if user.role != BETA_ROLE:
        return {"has_limit": False, "usage_percentage": None, "week_reset_at": None}

    usage = await _get_or_create_usage(db, user.id)
    await _reset_if_expired(db, usage)

    ratio = usage.total_cost_usd / BETA_WEEKLY_LIMIT
    percentage = min(int(ratio * 100), 100)
    week_reset_at = usage.week_start + timedelta(days=7)

    return {
        "has_limit": True,
        "usage_percentage": percentage,
        "week_reset_at": week_reset_at,
    }
