"""
Registra o `claude-sonnet-5` em `model_pricing`.

Execute via:
    python -m scripts.add_claude_sonnet_5

POR QUE ESTE SCRIPT EXISTE
`settings.news_writer_model` já aponta para `claude-sonnet-5` (config.py), e o
redator de notícias roda em produção com ele. Mas não havia linha de preço: como
`pricing.get_model_pricing` devolve `None` para modelo desconhecido e
`calculate_cost` então devolve `Decimal("0")`, todo o gasto do redator era
contabilizado como ZERO — sem erro, sem log, sem alarme.

Preços da tabela oficial da Anthropic, em USD por 1M de tokens:
    input  US$ 2,00
    output US$ 10,00

(Um terço a menos que o `claude-sonnet-4-6`, que custa 3,00/15,00 — é o que
torna a migração do modo clínico atraente. Ver T11 em `docs/plano-correcoes.md`;
esta linha de preço é pré-requisito daquela medição.)

Idempotente: atualiza se já existir.
"""

import argparse
import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.models import ModelPricing

MODEL_ID = "claude-sonnet-5"

INPUT_USD_POR_MILHAO = Decimal("2.00")
OUTPUT_USD_POR_MILHAO = Decimal("10.00")


async def add_sonnet_5(input_per_million: Decimal, output_per_million: Decimal) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(ModelPricing).where(ModelPricing.model_id == MODEL_ID)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.input_per_million = input_per_million
            existing.output_per_million = output_per_million
            existing.status = True
            await session.commit()
            print(f"[OK] {MODEL_ID} atualizado.")
        else:
            session.add(ModelPricing(
                model_id=MODEL_ID,
                provider="Anthropic",
                provider_type="anthropic",
                display_name="Claude Sonnet 5",
                input_per_million=input_per_million,
                output_per_million=output_per_million,
                status=True,
            ))
            await session.commit()
            print(f"[OK] {MODEL_ID} adicionado.")

        print(f"  - Input:  ${input_per_million} / 1M tokens")
        print(f"  - Output: ${output_per_million} / 1M tokens")
        print("  - Usado hoje pelo redator de notícias (settings.news_writer_model).")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Decimal, default=INPUT_USD_POR_MILHAO,
                        help="USD por 1M tokens de entrada")
    parser.add_argument("--output", type=Decimal, default=OUTPUT_USD_POR_MILHAO,
                        help="USD por 1M tokens de saída")
    args = parser.parse_args()
    asyncio.run(add_sonnet_5(args.input, args.output))
