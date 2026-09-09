"""
Identificação anônima de quem contribui com o mapa de DEA.

O módulo é público: não há conta, não há sessão. Ainda assim precisamos de
alguma noção de "mesma origem" para duas coisas concretas:

- impedir que quem cadastrou um DEA confirme o próprio registro;
- aplicar limite de submissões por origem.

Guardar o IP em claro resolveria as duas — e criaria um registro de
geolocalização de pessoas identificáveis, sem base legal (aqui não há contrato
nem consentimento; o `consent_logs` do produto cobre usuário logado, não este
caso). Então guardamos um hash.

## Por que o hash tem um bucket diário

`sha256(ip)` puro é reversível por força bruta trivial: o espaço IPv4 inteiro
tem ~4 bilhões de entradas, e uma GPU percorre isso em minutos. Um sal fixo
resolveria a força bruta, mas ainda permitiria correlacionar a mesma origem por
meses — que é exatamente o rastreamento que não queremos poder fazer.

Incluir a data no material do hash faz ele rotacionar a cada 24 h. Isso preserva
o que precisamos (dedupe e rate limit dentro do dia) e destrói o que não
queremos poder fazer (seguir uma origem ao longo do tempo).

O preço, aceito conscientemente: não dá para banir um IP permanentemente, nem
saber que a mesma origem cadastrou pins em março e em agosto.
"""

import hashlib
from datetime import date

from fastapi import Request


def _bucket_do_dia(momento: date | None = None) -> str:
    return (momento or date.today()).isoformat()


def hash_de_ip(ip: str, sal: str, momento: date | None = None) -> str:
    """`sha256(sal ‖ ip ‖ dia)` em hexadecimal (64 caracteres).

    O mesmo IP produz hashes diferentes em dias diferentes — é intencional, ver
    o docstring do módulo.
    """
    material = f"{sal}|{ip}|{_bucket_do_dia(momento)}".encode()
    return hashlib.sha256(material).hexdigest()


def ip_do_request(request: Request) -> str:
    """IP de origem, como o servidor o enxerga.

    ATENÇÃO — o valor devolvido aqui **não é confiável para defesa**: o container
    roda uvicorn com `--forwarded-allow-ips "*"` (ver `Dockerfile`), o que faz o
    ASGI aceitar o `X-Forwarded-For` de qualquer peer. Um cliente que troque esse
    header a cada requisição aparece como uma origem nova toda vez.

    Isto é registrado aqui, e não escondido, porque muda o peso das defesas do
    módulo: o limite por origem é redutor de ruído, e a barreira que realmente
    sustenta o mapa é o `status=pendente` mais o limite de densidade geográfica.
    Corrigir o `--forwarded-allow-ips` é trabalho à parte, que também beneficia
    login e OTP.
    """
    if request.client is not None and request.client.host:
        return request.client.host
    return "desconhecido"


def hash_do_request(request: Request, sal: str, momento: date | None = None) -> str:
    """Atalho para `hash_de_ip(ip_do_request(...))`."""
    return hash_de_ip(ip_do_request(request), sal, momento)
