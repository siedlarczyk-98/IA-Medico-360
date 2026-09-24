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

QUEM RODA
Só o processo líder (`app/core/lider.py`): coleta e classificação chamam o
modelo, e duas rodadas simultâneas custariam o dobro. Na sobreposição de um
deploy, a rede de segurança continua valendo: a coleta deduplica por
(source, external_id), o tagger e o redator usam
`with_for_update(skip_locked=True)`, e o digest tem unicidade por
(user_id, data_ref).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

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

# O laço dorme até a VIRADA da próxima hora, e não 3600 s depois de terminar.
# Dormir um intervalo fixo depois da rodada empurrava o relógio pela duração do
# pipeline: uma rodada às 10:59:30 que levasse 90 s acordava às 12:01, e a hora 11
# — a da coleta, ou a do resumo de uma faixa inteira — nunca era vista (item 62 de
# `docs/pitacos-do-fable-2.md`). A folga evita acordar um instante ANTES da virada
# por diferença entre o relógio do `sleep` e o de parede.
FOLGA_APOS_VIRADA_SEGUNDOS = 30

# Mesmo acordando na hora certa, uma hora pode escapar: rodada que falhou, líder
# trocado num deploy, pipeline que passou da virada. O laço guarda a última hora
# processada e recupera as que faltaram. Reprocessar é seguro — a coleta deduplica
# e o digest é único por (usuário, dia) —, mas só até este limite: um resumo da
# manhã entregue à noite já não é o que o médico pediu.
MAX_HORAS_RECUPERADAS = 3

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


async def _uma_rodada(hora: datetime) -> None:
    """Tudo o que cabe a `hora` (UTC, cheia): a coleta, se for a hora dela, e os digests."""
    settings = get_settings()

    async with async_session_factory() as db:
        if hora.hour == settings.news_run_hour:
            resultado = await rodar_pipeline(db)
            logger.info("Pipeline de notícias concluído", extra=resultado)

        # TODA HORA, e não mais só às `news_digest_hour`: quem decide se é a
        # hora de cada médico é a agenda dele (`news_digest_agenda`), lá dentro.
        # A rodada é barata quando não é hora de ninguém — uma consulta de
        # usuários e nenhum envio. A hora vai explícita: numa hora recuperada,
        # o relógio já está na seguinte, e é a faixa da perdida que se quer servir.
        resumo = await news_digest_service.enviar_digests(db, agora=hora)
        logger.info("Rodada de digest concluída", extra=resumo)


def hora_cheia(momento: datetime) -> datetime:
    return momento.replace(minute=0, second=0, microsecond=0)


def horas_a_processar(ultima: datetime | None, agora: datetime) -> list[datetime]:
    """
    As horas cheias que ainda não foram servidas, da mais antiga à atual.

    Sem `ultima` (primeira rodada do processo, ou liderança recém-assumida), só a
    atual: este processo não sabe o que o anterior já serviu. Num deploy isso não
    perde nada — o líder novo assume em menos de três minutos, dentro da mesma
    hora ou logo na virada, e repetir a hora que o antigo já tinha servido é seguro.
    """
    atual = hora_cheia(agora)
    if ultima is None:
        return [atual]
    horas = []
    hora = ultima + timedelta(hours=1)
    while hora <= atual:
        horas.append(hora)
        hora += timedelta(hours=1)
    descartadas = horas[:-MAX_HORAS_RECUPERADAS]
    if descartadas:
        logger.warning(
            "Notícias: %d hora(s) sem rodada ficaram para trás além do limite de "
            "recuperação (%s a %s UTC); digests dessas faixas não serão enviados",
            len(descartadas), descartadas[0].isoformat(), descartadas[-1].isoformat(),
        )
    return horas[-MAX_HORAS_RECUPERADAS:]


def segundos_ate_proxima_hora(agora: datetime) -> float:
    proxima = hora_cheia(agora) + timedelta(hours=1)
    return (proxima - agora).total_seconds() + FOLGA_APOS_VIRADA_SEGUNDOS


async def processar_pendentes(ultima: datetime | None, agora: datetime) -> datetime | None:
    """
    Roda cada hora pendente, em ordem. Devolve a última hora servida com sucesso.

    Para na primeira falha, sem avançar: a hora que falhou é tentada de novo na
    próxima volta, como hora recuperada.
    """
    for hora in horas_a_processar(ultima, agora):
        if hora != hora_cheia(agora):
            logger.warning("Notícias: recuperando a rodada das %s UTC, que tinha sido pulada", hora.isoformat())
        try:
            await _uma_rodada(hora)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Uma falha não pode matar o laço: sem isto, um erro transitório de
            # rede encerraria o agendamento em silêncio — exatamente o modo de
            # falha que este módulo existe para eliminar.
            logger.exception("Rodada de notícias falhou; nova tentativa no próximo ciclo: %s", exc)
            break
        ultima = hora
    return ultima


async def _laco() -> None:
    await asyncio.sleep(ATRASO_INICIAL_SEGUNDOS)
    ultima: datetime | None = None
    while True:
        ultima = await processar_pendentes(ultima, datetime.now(UTC))
        await asyncio.sleep(segundos_ate_proxima_hora(datetime.now(UTC)))


def iniciar() -> asyncio.Task | None:
    """Dispara o laço em background. Chamado no lifespan da aplicação."""
    settings = get_settings()
    if not settings.news_enabled:
        logger.info("Pipeline de notícias desligado (NEWS_ENABLED=false)")
        return None

    logger.info(
        "Pipeline de notícias ativo (coleta às %dh UTC; digest a cada hora, "
        "na faixa que cada médico escolheu)",
        settings.news_run_hour,
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
