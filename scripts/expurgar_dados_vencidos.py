"""
Expurgo de dados vencidos (LGPD art. 16).

NÃO AGENDE ISTO COMO CRON. O expurgo diário roda DENTRO da aplicação
(`app/services/expurgo_agendado.py`, ligado no `lifespan`). Este cabeçalho mandava
configurar um cron job no Railway — e foi exatamente esse cron que parou sem avisar
e deixou a retenção 39 dias sem rodar (2026-08-27). Um agendamento fora do processo
não tem quem perceba que ele morreu; o de dentro tem teste
(`tests/test_agendadores_ciclo_de_vida.py`) e vigilância.

Este script ficou para execução MANUAL — conferir depois de um incidente, ou forçar
uma rodada:

    python -m scripts.expurgar_dados_vencidos

É idempotente e seguro para rodar quantas vezes quiser. Os prazos vivem em
`app/services/data_subject_service.py`, não aqui — este arquivo é só o gatilho.
"""

import asyncio
import logging

from app.core.database import async_session_factory
from app.core.logging_config import setup_logging
from app.services.data_subject_service import expurgar_dados_vencidos


async def main() -> None:
    setup_logging(level="INFO", json_output=True)
    log = logging.getLogger("scripts.expurgo")

    async with async_session_factory() as db:
        contagem = await expurgar_dados_vencidos(db)

    log.info("Expurgo concluído", extra=contagem)
    for categoria, quantidade in contagem.items():
        print(f"  {categoria}: {quantidade}")


if __name__ == "__main__":
    asyncio.run(main())
