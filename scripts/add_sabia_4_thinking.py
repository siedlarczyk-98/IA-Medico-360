"""
Registra o `sabia-4-thinking` (Maritaca) em `model_pricing` — o modelo do modo
DATA_OCEAN.

Execute via:
    python -m scripts.add_sabia_4_thinking

OS PREÇOS DA MARITACA SÃO EM REAIS; A TABELA DO PROJETO É EM DÓLAR
Tabela publicada para o sabia-4-thinking: R$ 5,00 por 1M tokens de entrada e
R$ 40,00 por 1M de saída. Convertidos por `pricing.BRL_POR_USD` (fixo em 5,20),
viram US$ 0,9615 e US$ 7,6923 — que é o que vai para o banco, porque
`calculate_cost` e todo o resto do sistema calculam em USD.

O câmbio fixo é um gap conhecido e aceito: ver o comentário de `BRL_POR_USD`
em `app/services/pricing.py`.

Os valores podem ser sobrescritos por `--input`/`--output` (já em USD) quando a
tabela da Maritaca mudar antes de este script ser atualizado.

O CUSTO POR TOKEN NÃO É O CUSTO TOTAL
`data_ocean: true` liga junto `web_search` e `code_execution`, e as três são
cobradas por USO: GB processados, páginas lidas e minutos de execução. Esses
preços vivem em `pricing.PRECOS_FERRAMENTAS_BRL` e são somados ao custo da
interação a partir de `usage.tool_execution_details` — não passam por aqui.
"""

import argparse
import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.models import ModelPricing
from app.services.pricing import BRL_POR_USD

MODEL_ID = "sabia-4-thinking"


async def add_sabia(input_per_million: Decimal, output_per_million: Decimal) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(
            select(ModelPricing).where(ModelPricing.model_id == MODEL_ID)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Atualiza em vez de sair: preço de modelo muda, e obrigar a mexer
            # no banco na mão para corrigir um valor é como preços ficam velhos.
            existing.input_per_million = input_per_million
            existing.output_per_million = output_per_million
            existing.status = True
            await session.commit()
            print(f"[OK] {MODEL_ID} atualizado.")
        else:
            session.add(ModelPricing(
                model_id=MODEL_ID,
                provider="Maritaca",
                provider_type="maritaca",
                display_name="Sabiá 4 Thinking (Data Ocean)",
                input_per_million=input_per_million,
                output_per_million=output_per_million,
                status=True,
            ))
            await session.commit()
            print(f"[OK] {MODEL_ID} adicionado.")

        print(f"  - Input:  ${input_per_million} / 1M tokens")
        print(f"  - Output: ${output_per_million} / 1M tokens")
        print("  - (convertido de BRL por BRL_POR_USD, câmbio fixo)")
        print("  - O custo das ferramentas é somado à parte, a partir de")
        print("    tool_execution_details — ver pricing.PRECOS_FERRAMENTAS_BRL.")

    await engine.dispose()


# Tabela da Maritaca em BRL por 1M de tokens, convertida na hora do uso.
# Mantida em reais pelo mesmo motivo de `PRECOS_FERRAMENTAS_BRL`: é o número
# que dá para conferir contra a página de preços e contra a fatura.
INPUT_BRL_POR_MILHAO = Decimal("5.00")
OUTPUT_BRL_POR_MILHAO = Decimal("40.00")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Decimal, default=None,
                        help="USD por 1M tokens de entrada (sobrescreve a tabela embutida)")
    parser.add_argument("--output", type=Decimal, default=None,
                        help="USD por 1M tokens de saída (sobrescreve a tabela embutida)")
    args = parser.parse_args()

    entrada = args.input if args.input is not None else (
        (INPUT_BRL_POR_MILHAO / BRL_POR_USD).quantize(Decimal("0.0001"))
    )
    saida = args.output if args.output is not None else (
        (OUTPUT_BRL_POR_MILHAO / BRL_POR_USD).quantize(Decimal("0.0001"))
    )
    asyncio.run(add_sabia(entrada, saida))
