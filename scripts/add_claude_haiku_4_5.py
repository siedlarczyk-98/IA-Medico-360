"""
Registra o `claude-haiku-4-5` em `model_pricing`.

Execute via:
    python -m scripts.add_claude_haiku_4_5

POR QUE ESTE SCRIPT EXISTE
O Haiku atende dois caminhos em produção — a descrição de imagem de anexo
(`file_extractor_service.extract_image`, cobrada em `uploads.py`) e a limpeza de
seções de bula (`pharmadb_service._limpar_secoes_bula`) — e NUNCA esteve na
tabela de preços.

Como `pricing.get_model_pricing` devolve `None` para modelo desconhecido e
`calculate_cost` então devolve `Decimal("0")`, o `record_cost` do upload de
imagem vinha somando ZERO ao medidor semanal. O código sempre esteve correto; o
dado é que não existia — e o sintoma é o pior possível, porque parece
contabilizado.

Descoberto em 2026-09-15, ao cruzar os modelos usados pelo código com os
cadastrados no banco. Não é regressão da migração para o Sonnet 5: a linha
nunca existiu, nem com o ID datado (`claude-haiku-4-5-20251001`) que o código
usava antes.

Preços da tabela oficial da Anthropic, em USD por 1M de tokens:
    input  US$ 1,00
    output US$ 5,00

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

MODEL_ID = "claude-haiku-4-5"

INPUT_USD_POR_MILHAO = Decimal("1.00")
OUTPUT_USD_POR_MILHAO = Decimal("5.00")


async def add_haiku(input_per_million: Decimal, output_per_million: Decimal) -> None:
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
                display_name="Claude Haiku 4.5",
                input_per_million=input_per_million,
                output_per_million=output_per_million,
                status=True,
            ))
            await session.commit()
            print(f"[OK] {MODEL_ID} adicionado.")

        print(f"  - Input:  ${input_per_million} / 1M tokens")
        print(f"  - Output: ${output_per_million} / 1M tokens")
        print("  - Usado na descrição de imagem de anexo e na limpeza de bula.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Decimal, default=INPUT_USD_POR_MILHAO,
                        help="USD por 1M tokens de entrada")
    parser.add_argument("--output", type=Decimal, default=OUTPUT_USD_POR_MILHAO,
                        help="USD por 1M tokens de saída")
    args = parser.parse_args()
    asyncio.run(add_haiku(args.input, args.output))
