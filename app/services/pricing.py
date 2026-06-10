
from decimal import Decimal

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ModelPricing

# In-memory cache — ModelPricing é estático (muda raramente), TTL de 1h
_pricing_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)


async def get_model_pricing(db: AsyncSession, model_id: str) -> ModelPricing | None:
    """Retorna ModelPricing com cache em memória (TTL 1h)."""
    if model_id in _pricing_cache:
        return _pricing_cache[model_id]
    result = await db.execute(
        select(ModelPricing).where(
            ModelPricing.model_id == model_id,
            ModelPricing.status == True,
        )
    )
    pricing = result.scalar_one_or_none()
    if pricing is not None:
        _pricing_cache[model_id] = pricing
    return pricing


async def calculate_cost(
    db: AsyncSession,
    model_id: str,
    tokens_in: int | None,
    tokens_out: int | None,
) -> Decimal:
    """Calcula o custo em USD de uma chamada a um modelo."""
    pricing = await get_model_pricing(db, model_id)
    if not pricing:
        return Decimal("0")

    cost_in = Decimal(str(tokens_in or 0)) * pricing.input_per_million / Decimal("1000000")
    cost_out = Decimal(str(tokens_out or 0)) * pricing.output_per_million / Decimal("1000000")

    return (cost_in + cost_out).quantize(Decimal("0.000001"))
