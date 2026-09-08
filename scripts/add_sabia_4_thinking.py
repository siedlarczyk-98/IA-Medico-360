"""
Registra o `sabia-4-thinking` (Maritaca) em `model_pricing` — o modelo do modo
DATA_OCEAN.

Execute via:
    python -m scripts.add_sabia_4_thinking --input 5.00 --output 15.00

POR QUE OS PREÇOS SÃO OBRIGATÓRIOS NA LINHA DE COMANDO
Os demais scripts deste diretório trazem o preço embutido, copiado da página do
provedor no dia em que foram escritos. Aqui não dá: a documentação das
ferramentas integradas não publica a tabela, e um preço chutado é pior que
preço nenhum — ele produz relatórios de custo que PARECEM certos.

Sem os valores reais, este script recusa rodar.

ATENÇÃO — O CUSTO POR TOKEN NÃO É O CUSTO TOTAL
`data_ocean: true` liga junto `web_search` e `code_execution`, e as três são
cobradas por USO, não por token: GB processados, páginas lidas e minutos de
execução. Esses valores voltam em `usage.tool_execution_details` e são
guardados crus em `ProviderResponse.tool_usage`. A conversão para dólar depende
de uma tabela que ainda não temos — enquanto ela não existir, o custo gravado
para este modo é APENAS o de tokens, e portanto está subestimado.
"""

import argparse
import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models.models import ModelPricing

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
        print("  - AVISO: o custo das ferramentas (Data Ocean, busca, código)")
        print("           NÃO está incluído — ver o cabeçalho deste script.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Decimal,
                        help="USD por 1M tokens de entrada (da tabela de preços da Maritaca)")
    parser.add_argument("--output", required=True, type=Decimal,
                        help="USD por 1M tokens de saída")
    args = parser.parse_args()
    asyncio.run(add_sabia(args.input, args.output))
