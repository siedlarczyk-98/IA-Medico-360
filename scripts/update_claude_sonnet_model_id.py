"""
Atualiza o model_id do Claude Sonnet de claude-sonnet-4-20250514 para claude-sonnet-4-6.
Execute via: python -m scripts.update_claude_sonnet_model_id
"""

import asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.models import ModelPricing


OLD_ID = "claude-sonnet-4-20250514"
NEW_ID = "claude-sonnet-4-6"


async def update_model_id():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(ModelPricing).where(ModelPricing.model_id == OLD_ID)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            print(f"[INFO] Modelo '{OLD_ID}' nao encontrado no banco. Nada a fazer.")
            return

        existing.model_id = NEW_ID
        await session.commit()
        print(f"[OK] Model ID atualizado: {OLD_ID} -> {NEW_ID}")


if __name__ == "__main__":
    asyncio.run(update_model_id())
