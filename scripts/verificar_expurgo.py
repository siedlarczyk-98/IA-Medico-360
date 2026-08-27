"""
Diagnóstico: o expurgo de dados vencidos está mesmo rodando?

Não muda nada — só conta o que já passou do prazo e ainda está no banco.

    python -m scripts.verificar_expurgo

Sai com código 1 quando encontra passivo, para poder ser usado como alarme.

Existe porque a política de retenção (LGPD art. 16) está implementada em
`data_subject_service` e agendada por cron no painel do Railway — fora do
repositório. Se o agendamento for removido, pausado ou falhar, nada avisa: o
código continua correto, os testes continuam verdes e o dado vencido só se
acumula em silêncio.

Foi exatamente o que aconteceu: em 2026-08-27 havia 14 imagens além dos 30 dias
ainda com o base64 no banco, e 8 já expurgadas — sinal de um job que rodou e
parou.
"""

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models.models import FileExtraction
from app.services.data_subject_service import (
    RETENCAO_ARQUIVO_DIAS,
    RETENCAO_IMAGEM_DIAS,
)


def _limite(dias: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=dias)


async def main() -> int:
    async with async_session_factory() as db:
        imagens_vencidas = (await db.execute(
            select(func.count())
            .select_from(FileExtraction)
            .where(
                FileExtraction.image_base64.is_not(None),
                FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
            )
        )).scalar_one()

        arquivos_vencidos = (await db.execute(
            select(func.count())
            .select_from(FileExtraction)
            .where(FileExtraction.created_at < _limite(RETENCAO_ARQUIVO_DIAS))
        )).scalar_one()

        mais_antigo_vencido = (await db.execute(
            select(func.min(FileExtraction.created_at))
            .where(
                FileExtraction.image_base64.is_not(None),
                FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
            )
        )).scalar_one()

    print("Passivo de expurgo (LGPD art. 16)\n")
    print(f"  imagens além de {RETENCAO_IMAGEM_DIAS} dias com base64 : {imagens_vencidas}")
    print(f"  arquivos além de {RETENCAO_ARQUIVO_DIAS} dias           : {arquivos_vencidos}")

    if not imagens_vencidas and not arquivos_vencidos:
        print("\nOK — nada vencido. O expurgo está em dia.")
        return 0

    if mais_antigo_vencido:
        atraso = (datetime.now(UTC) - mais_antigo_vencido).days - RETENCAO_IMAGEM_DIAS
        print(f"\n  registro vencido mais antigo: {mais_antigo_vencido:%Y-%m-%d} "
              f"({atraso} dias além do prazo)")

    print("\nPASSIVO ENCONTRADO — o cron provavelmente não está rodando.")
    print("Verifique o agendamento no painel do Railway e rode:")
    print("    python -m scripts.expurgar_dados_vencidos")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
