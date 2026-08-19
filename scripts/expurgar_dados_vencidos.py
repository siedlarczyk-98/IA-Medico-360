"""
Expurgo de dados vencidos (LGPD art. 16).

Rodar diariamente. No Railway, como cron job:

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
