"""
Pipeline de notícias rodando dentro do próprio backend.

POR QUE AQUI, E NÃO NUM CRON
O módulo veio de um repositório onde ele era um Cron Job do painel do Railway —
fora do repositório, invisível a testes, ao CI e a code review. Este projeto já
pagou esse preço duas vezes: o expurgo LGPD parou por 39 dias sem ninguém saber,
e o cache semântico ficou meses desligado. Ver o cabeçalho de
`app/services/expurgo_agendado.py`, que é o padrão seguido aqui.

Trazer o agendamento para o código faz dele algo que aparece no diff, tem teste,
e não pode sumir sem que o backend inteiro caia junto.

O QUE ISSO CUSTA
Com várias réplicas, todas rodam o pipeline. É inofensivo por construção: a
coleta deduplica por (source, external_id), o tagger e o redator usam
`with_for_update(skip_locked=True)`, e o digest tem unicidade por
(user_id, data_ref). Eleição de líder seria complexidade sem ganho nesta escala.
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.services import (
    news_collector_service,
    news_digest_service,
    news_tagger_service,
    news_writer_service,
)

logger = logging.getLogger(__name__)

# De hora em hora o laço acorda e confere se já passou da hora configurada. Uma
# checagem barata por hora é mais robusta que calcular o sono exato até o próximo
# horário: reinício, deploy ou drift de relógio não fazem a rodada do dia sumir.
INTERVALO_CHECAGEM_SEGUNDOS = 3600

# O boot já carrega o modelo de NER e as fórmulas; somar chamada de rede na mesma
# janela atrasaria a primeira requisição de verdade.
ATRASO_INICIAL_SEGUNDOS = 120


async def rodar_pipeline(db: AsyncSession) -> dict:
    """
    Coleta -> tagging -> redação/publicação, em sequência.

    A ordem importa: o tagger precisa do artigo coletado, e o redator só pega
    itens `tagged` — assim nenhum texto é publicado sem tema, o que o deixaria
    invisível no feed de todo mundo.
    """
    coleta = await news_collector_service.coletar_do_dia(db)
    await db.commit()

    tagging = await news_tagger_service.taggear_lote(db)
    await db.commit()

    redacao = await news_writer_service.redigir_lote(db)
    await db.commit()

    return {"coleta": coleta, "tagging": tagging, "redacao": redacao}


async def _uma_rodada() -> None:
    settings = get_settings()
    agora = datetime.now(UTC)

    async with async_session_factory() as db:
        if agora.hour == settings.news_run_hour:
            resultado = await rodar_pipeline(db)
            logger.info("Pipeline de notícias concluído", extra=resultado)

        if agora.hour == settings.news_digest_hour:
            resumo = await news_digest_service.enviar_digests(db)
            logger.info("Rodada de digest concluída", extra=resumo)


async def _laco() -> None:
    await asyncio.sleep(ATRASO_INICIAL_SEGUNDOS)
    while True:
        try:
            await _uma_rodada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Uma falha não pode matar o laço: sem isto, um erro transitório de
            # rede encerraria o agendamento em silêncio — exatamente o modo de
            # falha que este módulo existe para eliminar.
            logger.exception("Rodada de notícias falhou; nova tentativa no próximo ciclo: %s", exc)
        await asyncio.sleep(INTERVALO_CHECAGEM_SEGUNDOS)


def iniciar() -> asyncio.Task | None:
    """Dispara o laço em background. Chamado no lifespan da aplicação."""
    settings = get_settings()
    if not settings.news_enabled:
        logger.info("Pipeline de notícias desligado (NEWS_ENABLED=false)")
        return None

    logger.info(
        "Pipeline de notícias ativo (coleta às %dh UTC, digest às %dh UTC)",
        settings.news_run_hour, settings.news_digest_hour,
    )
    return asyncio.create_task(_laco(), name="noticias-agendado")


async def parar(tarefa: asyncio.Task | None) -> None:
    """Encerra o laço no shutdown, sem deixar tarefa órfã reclamando no log."""
    if tarefa is None or tarefa.done():
        return
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass
