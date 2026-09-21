"""
Heartbeat do stream: conexão muda não pode parecer conexão morta.

O orquestrador passa até ~30 s sem emitir nada (modelo "pensando", verificação de
referências). Proxy de hospital e balanceador cortam conexão ociosa, e o médico
via a resposta parar no meio com o custo do modelo já pago.
"""

import asyncio
import contextvars

import pytest

from app.core.sse import PING, com_heartbeat

RAPIDO = 0.02  # intervalo de ping nos testes


async def _coletar(iterador) -> list[str]:
    return [frame async for frame in iterador]


async def test_frames_passam_intactos_e_na_ordem():
    async def gerador():
        yield "event: start\ndata: {}\n\n"
        yield "event: done\ndata: {}\n\n"

    frames = await _coletar(com_heartbeat(gerador(), intervalo=RAPIDO))

    assert frames == ["event: start\ndata: {}\n\n", "event: done\ndata: {}\n\n"]


async def test_silencio_longo_vira_ping_e_a_resposta_chega_depois():
    async def gerador():
        yield "event: start\ndata: {}\n\n"
        await asyncio.sleep(RAPIDO * 5)  # o modelo pensando
        yield "event: token\ndata: {}\n\n"

    frames = await _coletar(com_heartbeat(gerador(), intervalo=RAPIDO))

    assert frames[0].startswith("event: start")
    assert frames[-1].startswith("event: token")
    assert frames.count(PING) >= 2
    assert set(frames[1:-1]) == {PING}


def test_o_ping_e_comentario_sse_que_o_leitor_do_frontend_ignora():
    """O leitor só olha linhas `event: ` e `data: `; comentário começa com `:`."""
    assert PING.startswith(":")
    assert PING.endswith("\n\n")
    assert not any(linha.startswith(("event: ", "data: ")) for linha in PING.split("\n"))


async def test_erro_do_gerador_chega_ao_consumidor_depois_dos_frames():
    async def gerador():
        yield "event: start\ndata: {}\n\n"
        raise RuntimeError("falha no meio do stream")

    recebidos = []
    with pytest.raises(RuntimeError, match="falha no meio"):
        async for frame in com_heartbeat(gerador(), intervalo=RAPIDO):
            recebidos.append(frame)

    assert recebidos == ["event: start\ndata: {}\n\n"]


async def test_cliente_que_desconecta_cancela_a_chamada_ao_modelo():
    """Propriedade que o stream já tinha e não pode ter perdido."""
    cancelado = asyncio.Event()

    async def gerador():
        yield "event: start\ndata: {}\n\n"
        try:
            await asyncio.sleep(60)  # a chamada ao modelo
        except asyncio.CancelledError:
            cancelado.set()
            raise

    iterador = com_heartbeat(gerador(), intervalo=RAPIDO)
    assert (await anext(iterador)).startswith("event: start")

    await asyncio.wait_for(iterador.aclose(), timeout=2)  # o cliente foi embora

    assert cancelado.is_set()


async def test_cliente_lento_nao_acumula_a_resposta_em_memoria():
    produzidos = []

    async def gerador():
        for i in range(50):
            produzidos.append(i)
            yield f"data: {i}\n\n"

    iterador = com_heartbeat(gerador(), intervalo=1)
    await anext(iterador)
    await asyncio.sleep(RAPIDO)  # dá tempo ao produtor de correr, se pudesse

    assert len(produzidos) <= 3, f"o produtor disparou na frente do cliente: {len(produzidos)}"
    await iterador.aclose()


async def test_o_gerador_roda_inteiro_na_mesma_tarefa():
    """O motivo do desenho: o tracing guarda o span em `contextvars`, por tarefa."""
    marca: contextvars.ContextVar[str] = contextvars.ContextVar("marca", default="vazio")
    vistos = []

    async def gerador():
        marca.set("span-aberto")
        yield "a\n\n"
        await asyncio.sleep(RAPIDO * 3)
        vistos.append(marca.get())
        yield "b\n\n"
        vistos.append(marca.get())

    await _coletar(com_heartbeat(gerador(), intervalo=RAPIDO))

    assert vistos == ["span-aberto", "span-aberto"]
