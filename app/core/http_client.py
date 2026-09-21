"""
Médico 360 — Cliente HTTP assíncrono compartilhado.

Um único httpx.AsyncClient é reutilizado por toda a aplicação para aproveitar
keep-alive de conexões (evita handshake TLS/DNS a cada chamada externa).
Inicializado no lifespan da app (main.py) e fechado no shutdown.

Os timeouts são por-requisição: passe `timeout=` em cada chamada (.post/.get/.stream)
quando precisar de um valor diferente do padrão.
"""

import httpx

_client: httpx.AsyncClient | None = None
_stream_client: httpx.AsyncClient | None = None

_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)
_DEFAULT_TIMEOUT = httpx.Timeout(30.0)

# DOIS POOLS, e a separação é por DURAÇÃO da chamada.
#
# Uma resposta em streaming segura a conexão HTTP dela por 13 a 57 segundos. Com
# um pool só, perto de 80 respostas simultâneas ocupavam as 100 conexões, e tudo o
# que é curto e crítico — triagem, login pela Curseduca, PharmaDB, PubMed —
# entrava na fila atrás delas: o login falhava porque alguém, em outro lugar,
# estava lendo uma resposta longa. Cada excedente ainda gastava os 30 s do
# `pool` timeout antes de cair para o modelo de contingência.
#
# O pool de streams é maior porque cada stream É uma conexão; o teto real de
# respostas simultâneas passa a ser ele, e não mais um número que as chamadas
# curtas dividiam sem saber. `pool=5`: pool cheio falha rápido em vez de pendurar.
_STREAM_LIMITS = httpx.Limits(max_connections=300, max_keepalive_connections=40)
_STREAM_TIMEOUT = httpx.Timeout(30.0, pool=5.0)


async def startup() -> None:
    global _client, _stream_client
    if _client is None:
        _client = httpx.AsyncClient(limits=_LIMITS, timeout=_DEFAULT_TIMEOUT)
    if _stream_client is None:
        _stream_client = httpx.AsyncClient(limits=_STREAM_LIMITS, timeout=_STREAM_TIMEOUT)


async def shutdown() -> None:
    global _client, _stream_client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _stream_client is not None:
        await _stream_client.aclose()
        _stream_client = None


def get_client() -> httpx.AsyncClient:
    """
    Retorna o client compartilhado. Faz lazy-init caso o lifespan não tenha
    rodado (ex.: testes), garantindo que nunca retorne None.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(limits=_LIMITS, timeout=_DEFAULT_TIMEOUT)
    return _client


def get_stream_client() -> httpx.AsyncClient:
    """Client das respostas em STREAMING dos modelos. Ver o comentário dos pools."""
    global _stream_client
    if _stream_client is None:
        _stream_client = httpx.AsyncClient(limits=_STREAM_LIMITS, timeout=_STREAM_TIMEOUT)
    return _stream_client
