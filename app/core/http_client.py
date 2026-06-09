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

_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)
_DEFAULT_TIMEOUT = httpx.Timeout(30.0)


async def startup() -> None:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(limits=_LIMITS, timeout=_DEFAULT_TIMEOUT)


async def shutdown() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_client() -> httpx.AsyncClient:
    """
    Retorna o client compartilhado. Faz lazy-init caso o lifespan não tenha
    rodado (ex.: testes), garantindo que nunca retorne None.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(limits=_LIMITS, timeout=_DEFAULT_TIMEOUT)
    return _client
