"""
Script para adicionar Gemini 2.5 Flash ao banco de dados.
Execute via: python -m scripts.add_gemini_2_5_flash
"""

import asyncio
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.models import ModelPricing


async def add_gemini_2_5_flash():
    """Adiciona o modelo Gemini 2.5 Flash à tabela model_pricing."""
    settings = get_settings()

    # Criar engine e session
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Verificar se já existe
        result = await session.execute(
            select(ModelPricing).where(ModelPricing.model_id == "gemini-2.5-flash")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print("[OK] Gemini 2.5 Flash ja existe no banco")
            return

        # Precos conforme Google AI API (atualizado para 2.5 Flash)
        # https://ai.google.dev/pricing
        model = ModelPricing(
            model_id="gemini-2.5-flash",
            provider="Google",
            provider_type="google",
            display_name="Gemini 2.5 Flash",
            input_per_million=Decimal("0.075"),      # $0.075 por 1M tokens (input)
            output_per_million=Decimal("0.30"),      # $0.30 por 1M tokens (output)
            status=True,
        )

        session.add(model)
        await session.commit()

        print("[OK] Gemini 2.5 Flash adicionado com sucesso!")
        print(f"  - Model ID: gemini-2.5-flash")
        print(f"  - Input: $0.075 / 1M tokens")
        print(f"  - Output: $0.30 / 1M tokens")


if __name__ == "__main__":
    asyncio.run(add_gemini_2_5_flash())
