"""
Rate limit da API.

## A chave é o USUÁRIO, e o IP só quando não há usuário

Era só o IP. Um hospital inteiro sai por um endereço (NAT), então todos os
médicos de lá dividiam as mesmas 30 perguntas por minuto: um plantão movimentado
derrubava o colega da sala ao lado com 429. Com token na requisição, cada médico
tem a própria cota; o IP continua valendo para as rotas públicas (login, código
por e-mail, DEA, páginas de captação), onde não há a quem atribuir.

O token é só DECODIFICADO aqui, sem ir ao banco: a chave precisa existir antes do
handler e custar nada. Não é decisão de acesso — token forjado não passa pela
assinatura e cai na chave por IP; token válido de usuário desativado é barrado
depois, em `get_current_user`. O pior que um token inválido consegue é ser
limitado pelo IP, que é o comportamento de antes.

## O contador mora no Redis, com reserva em memória

Em memória, o limite valia POR PROCESSO: com N workers ou réplicas, cada limite
virava N vezes o declarado — e a fase de capacidade do plano quer justamente
subir workers (a máquina tem 8 vCPU e a API usa uma). Com o Redis fora do ar o
slowapi cai para a contagem em memória sozinho e volta quando o Redis volta: o
limite afrouxa, não some, e nenhuma requisição falha por causa do limitador.

## Sobre o IP

`get_remote_address` lê `request.client.host`, que o uvicorn preenche a partir do
`X-Forwarded-For` (`--forwarded-allow-ips "*"` no Dockerfile). Conferido em
produção em 2026-09-21: a borda do Railway SOBRESCREVE o cabeçalho, então o
cliente não consegue forjar o próprio IP. Se a API for um dia para trás de outro
proxy, isso precisa ser conferido de novo.
"""

import jwt as pyjwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import get_settings

COOKIE_DE_SESSAO = "medico360_session"


def _token_da_requisicao(request: Request) -> str | None:
    autorizacao = request.headers.get("authorization", "")
    if autorizacao.lower().startswith("bearer "):
        return autorizacao[7:].strip()
    return request.cookies.get(COOKIE_DE_SESSAO)


def chave_do_limite(request: Request) -> str:
    """`user:<id>` quando há token com assinatura válida; senão, o IP."""
    token = _token_da_requisicao(request)
    if token:
        settings = get_settings()
        try:
            payload = pyjwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            if payload.get("sub"):
                return f"user:{payload['sub']}"
        except pyjwt.PyJWTError:
            pass
    return get_remote_address(request)


def _onde_contar() -> str:
    """Redis em produção; memória em desenvolvimento e na suíte de testes.

    Fora de produção o processo é um só, então a memória conta certo — e a suíte
    aponta o Redis para uma porta fechada de propósito (`tests/conftest.py`), onde
    o `limiter.reset()` de cada teste pagaria o timeout de conexão.
    """
    settings = get_settings()
    return settings.redis_url if settings.is_production else "memory://"


limiter = Limiter(
    key_func=chave_do_limite,
    storage_uri=_onde_contar(),
    # Timeouts curtos: o limitador roda em TODA requisição e não pode ser o que a
    # deixa lenta quando o Redis engasga.
    storage_options={"socket_connect_timeout": 1, "socket_timeout": 1},
    in_memory_fallback_enabled=True,
)
