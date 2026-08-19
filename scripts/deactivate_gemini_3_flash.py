"""
Script para desativar (status=False) o modelo gemini-3-flash em model_pricing.

O frontend não deve carregar exclusões de modelo hardcoded — a disponibilidade
é controlada pelo backend (campo `status` / `available`). Este script desativa o
gemini-3-flash para que ele não apareça na lista de modelos. É idempotente e um
no-op caso o modelo não exista.

Execute via: python -m scripts.deactivate_gemini_3_flash
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.models import ModelPricing


async def deactivate_gemini_3_flash():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(ModelPricing).where(ModelPricing.model_id == "gemini-3-flash")
        )
        model = result.scalar_one_or_none()

        if model is None:
            print("[OK] gemini-3-flash nao existe no banco — nada a fazer")
            return

        if model.status is False:
            print("[OK] gemini-3-flash ja esta desativado")
            return

        model.status = False
        await session.commit()
        print("[OK] gemini-3-flash desativado (status=False)")


if __name__ == "__main__":
    asyncio.run(deactivate_gemini_3_flash())
