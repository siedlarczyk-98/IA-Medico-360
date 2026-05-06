
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ModelPricing


async def calculate_cost(
    db: AsyncSession,
    model_id: str,
    tokens_in: int | None,
    tokens_out: int | None,
) -> Decimal:
    """
    Calcula o custo em USD de uma chamada a um modelo.
    Busca preços na tabela model_pricing.
    """
    result = await db.execute(
        select(ModelPricing).where(
            ModelPricing.model_id == model_id,
            ModelPricing.status == True,
        )
    )
    pricing = result.scalar_one_or_none()

    if not pricing:
        return Decimal("0")

    cost_in = Decimal(str(tokens_in or 0)) * pricing.input_per_million / Decimal("1000000")
    cost_out = Decimal(str(tokens_out or 0)) * pricing.output_per_million / Decimal("1000000")

    return (cost_in + cost_out).quantize(Decimal("0.000001"))