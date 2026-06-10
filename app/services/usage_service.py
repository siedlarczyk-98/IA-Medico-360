from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User, UserWeeklyUsage

BETA_WEEKLY_LIMIT = Decimal("1.00")
BETA_ROLE = "beta_user"


async def _get_or_create_usage(db: AsyncSession, user_id) -> UserWeeklyUsage:
    result = await db.execute(select(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user_id))
    usage = result.scalar_one_or_none()
    if usage is None:
        usage = UserWeeklyUsage(
            user_id=user_id,
            week_start=datetime.now(timezone.utc),
            total_cost_usd=Decimal("0"),
        )
        db.add(usage)
        await db.flush()
    return usage


async def _reset_if_expired(db: AsyncSession, usage: UserWeeklyUsage) -> None:
    now = datetime.now(timezone.utc)
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
