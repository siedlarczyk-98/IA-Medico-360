"""
Diagnóstico: a política de retenção está sendo cumprida?

Não apaga nada — só conta o que já passou do prazo e continua no banco.

    python -m scripts.verificar_expurgo

Sai com código 1 quando encontra passivo.

QUANDO USAR
O expurgo roda sozinho, dentro do backend, a cada 24h — ver
`app/services/expurgo_agendado.py`. Este script existe para responder à mão
"está em dia?", sem esperar o próximo ciclo e sem apagar nada: útil depois de
um incidente, ao investigar uma reclamação de LGPD, ou para conferir o estado
de um ambiente que ficou parado.

A medição vive em `data_subject_service.medir_passivo` — a mesma que a tarefa
agendada usa. Duas contagens diferentes para a mesma pergunta acabariam
divergindo, e a divergência apareceria como um dos dois mentindo.
"""

import asyncio
import logging
import sys

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.logging_config import setup_logging
from app.services.data_subject_service import (
    RETENCAO_ARQUIVO_DIAS,
    RETENCAO_IMAGEM_DIAS,
    medir_passivo,
)

logger = logging.getLogger("scripts.verificar_expurgo")


async def main() -> int:
    settings = get_settings()
    setup_logging(level=settings.log_level, json_output=settings.is_production)

    async with async_session_factory() as db:
        passivo = await medir_passivo(db)

    print("Passivo de retenção (LGPD art. 16)\n")
    print(f"  imagens além de {RETENCAO_IMAGEM_DIAS} dias com base64 : {passivo['imagens_vencidas']}")
    print(f"  arquivos além de {RETENCAO_ARQUIVO_DIAS} dias           : {passivo['arquivos_vencidos']}")

    if passivo["total"] == 0:
        print("\nOK — nada vencido.")
        logger.info("Retenção em dia", extra=passivo)
        return 0

    print(f"\n  atraso do mais antigo: {passivo['dias_de_atraso']} dias além do prazo")
    print("\nPASSIVO ENCONTRADO.")
    print("O expurgo roda a cada 24h dentro do backend; se há passivo, ou o backend")
    print("ficou fora do ar, ou a tarefa está falhando — confira o log por")
    print("'Rodada de expurgo falhou' e o Sentry pela tag alarme=expurgo_lgpd.")
    print("\nPara limpar agora:")
    print("    python -m scripts.expurgar_dados_vencidos")

    logger.warning("Retenção atrasada", extra=passivo)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
