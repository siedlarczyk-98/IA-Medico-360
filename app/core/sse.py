"""
Heartbeat para respostas SSE.

Um stream do orquestrador passa longos trechos sem emitir nada: o modelo
"pensando" antes do primeiro token (até ~30 s no raciocínio clínico), e a
verificação de referências entre o `text_done` e o `done`. Proxy corporativo de
hospital, balanceador e o próprio navegador tratam conexão muda como conexão
morta e a cortam — o médico vê a resposta parar no meio, e o custo do modelo já
foi pago.

`com_heartbeat` injeta um COMENTÁRIO SSE (`: ping`) sempre que o stream fica
parado. Comentário é parte do protocolo: o `EventSource` e o nosso leitor
(`frontend-app/src/api/orquestrador.ts`, que só olha `event:` e `data:`) ignoram
a linha, então nenhum cliente precisa mudar.

## Por que produtor + fila, e não uma corrida contra o relógio

A forma curta seria `asyncio.wait({anext(gerador)}, timeout=...)`. Ela faz cada
passo do gerador rodar numa tarefa diferente, e o tracing (OpenTelemetry) guarda
o span corrente em `contextvars`, que é por tarefa: o span aberto num passo não
existiria no seguinte, e o `detach` falharia por estar em outro contexto. Aqui o
gerador inteiro roda em UMA tarefa; só os frames atravessam, pela fila.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

PING = ": ping\n\n"
INTERVALO_PADRAO_S = 15.0

_FIM = object()


async def com_heartbeat(
    gerador: AsyncIterator[str], intervalo: float = INTERVALO_PADRAO_S
) -> AsyncIterator[str]:
    """Repassa os frames de `gerador`, com um `: ping` a cada `intervalo` de silêncio.

    Cancelar este iterador (cliente desconectou) cancela a tarefa produtora — e,
    com ela, a chamada ao modelo em andamento. É o comportamento que o stream já
    tinha, preservado.
    """
    # Tamanho 1: o produtor só avança quando o cliente consumiu. Sem isso um
    # cliente lento deixaria a resposta inteira acumular em memória.
    fila: asyncio.Queue = asyncio.Queue(maxsize=1)

    async def _produzir() -> None:
        try:
            async for frame in gerador:
                await fila.put(frame)
        except asyncio.CancelledError:
            # Quem cancela é o consumidor, que já foi embora: não há a quem avisar,
            # e um `put` aqui bloquearia para sempre numa fila cheia que ninguém lê.
            raise
        except Exception as exc:
            # `put` e não `put_nowait`: o consumidor está vivo e vai esvaziar a
            # fila; o erro precisa chegar DEPOIS dos frames já produzidos.
            await fila.put(exc)
        else:
            await fila.put(_FIM)

    produtor = asyncio.create_task(_produzir(), name="sse-produtor")
    try:
        while True:
            try:
                item = await asyncio.wait_for(fila.get(), timeout=intervalo)
            except TimeoutError:
                yield PING
                continue
            if item is _FIM:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        if not produtor.done():
            produtor.cancel()
        with suppress(BaseException):
            await produtor
