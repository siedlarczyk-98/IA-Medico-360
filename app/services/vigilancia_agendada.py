"""
Vigilância rodando dentro do próprio backend.

Mesma escolha de `expurgo_agendado`, pelo mesmo motivo: agendamento fora do
repositório é agendamento que some sem ninguém ver. Aqui ele aparece no diff,
tem teste, e só morre se o processo inteiro morrer — caso em que o health check
grita e o Railway reinicia.

O QUE ESTE LAÇO CONSEGUE E O QUE NÃO CONSEGUE
Consegue detectar uma garantia que parou de valer: cache que não grava, custo
que escalou, expurgo que não roda. Não consegue vigiar a si mesmo — se ESTA
tarefa morrer, nada avisa. Isso é um degrau a menos de silêncio, não zero, e a
honestidade sobre o limite importa mais do que fingir cobertura total.

O degrau restante é o processo. Ele já é observado de fora: `/api/v1/health` e
`/health/ready` são consultados pelo Railway, e um processo morto é ruidoso de
um jeito que um cron morto nunca foi.

ORDEM DE BOOT — CUIDADO AO MEXER
`ATRASO_INICIAL_SEGUNDOS` precisa ser confortavelmente MAIOR que o do
`expurgo_agendado` (90s). A vigilância alarma quando não encontra rastro de
expurgo em `audit_logs`; se ela rodasse antes da primeira rodada de expurgo,
alarmaria em todo boot de banco novo. Encurtar este número sem olhar aquele
produz um alarme falso recorrente — que é o começo de todo alarme ignorado.
"""

import asyncio
import logging
from datetime import UTC, datetime

from app.core.alarme import alarmar
from app.core.database import async_session_factory
from app.services.vigilancia_service import avaliar, medir_tudo

logger = logging.getLogger(__name__)

# Seis horas: um laço infinito de retry queima orçamento rápido demais para uma
# checagem diária, e as três consultas são três COUNT indexados — o custo de
# rodar é irrelevante perto do custo de descobrir tarde.
INTERVALO_HORAS = 6

# Ver "ORDEM DE BOOT" no cabeçalho antes de reduzir.
ATRASO_INICIAL_SEGUNDOS = 900

# Um alarme por tag por dia, no máximo. Sem isto, uma condição que persiste
# (cache quebrado por uma semana) rende quatro eventos diários e ensina todo
# mundo a arquivar sem ler — o mecanismo exato pelo qual um alarme deixa de
# proteger qualquer coisa.
#
# O registro é em memória e some no deploy, de propósito: depois de um deploy
# você QUER saber de novo se o problema continua de pé.
SILENCIO_POR_TAG_HORAS = 24

_ultimo_alarme: dict[str, datetime] = {}


def _deve_alarmar(tag: str, agora: datetime | None = None) -> bool:
    """Passou tempo suficiente desde o último alarme desta tag?"""
    agora = agora or datetime.now(UTC)
    anterior = _ultimo_alarme.get(tag)
    if anterior is not None and (agora - anterior).total_seconds() < SILENCIO_POR_TAG_HORAS * 3600:
        return False
    _ultimo_alarme[tag] = agora
    return True


async def _uma_rodada() -> None:
    """Mede, registra no log, e alarma só o que ainda não foi alarmado hoje."""
    async with async_session_factory() as db:
        medicoes = await medir_tudo(db)

    # O log sai sempre, mesmo sem alarme: é o histórico que permite responder
    # "desde quando?" quando o alarme finalmente chega.
    logger.info("Vigilância: medições do ciclo", extra=medicoes)

    for alarme in avaliar(medicoes):
        logger.warning("Vigilância: %s", alarme["mensagem"], extra=alarme["contexto"])
        if _deve_alarmar(alarme["tag"]):
            alarmar(
                tag=alarme["tag"],
                mensagem=alarme["mensagem"],
                contexto=alarme["contexto"],
            )


async def _laco() -> None:
    await asyncio.sleep(ATRASO_INICIAL_SEGUNDOS)
    while True:
        try:
            await _uma_rodada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Mesmo raciocínio de `expurgo_agendado`: uma falha transitória de
            # banco não pode encerrar em silêncio o laço que existe justamente
            # para eliminar falhas silenciosas.
            logger.exception("Rodada de vigilância falhou; tentando no próximo ciclo: %s", exc)
        await asyncio.sleep(INTERVALO_HORAS * 3600)


def iniciar() -> asyncio.Task:
    """Dispara o laço em background. Chamado no lifespan da aplicação."""
    logger.info(
        "Vigilância ativa (a cada %dh, primeira rodada em %ds)",
        INTERVALO_HORAS, ATRASO_INICIAL_SEGUNDOS,
    )
    return asyncio.create_task(_laco(), name="vigilancia-agendada")


async def parar(tarefa: asyncio.Task | None) -> None:
    """Encerra o laço no shutdown, sem deixar tarefa órfã reclamando no log."""
    if tarefa is None or tarefa.done():
        return
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass
