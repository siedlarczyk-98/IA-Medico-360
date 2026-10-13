"""
Interceptador do teste de carga: muda para ONDE e com QUAL MODELO o backend chama
os serviços externos, sem tocar no código do app.

Só entra no processo com esta pasta no PYTHONPATH
(`PYTHONPATH=/app/scripts/carga/interceptador`) — o Python importa `sitecustomize`
sozinho na partida, antes do app, em cada worker — e só age com as variáveis abaixo.

    CARGA_FALSO_URL       destino do servidor falso (`falso_externo.py`).
    CARGA_FALSO_HOSTS     quais hosts vão para o falso, separados por vírgula.
                          Vazio = TODOS os externos (etapa A, local). No teste com
                          provedores reais: só a Waid e o SendGrid, por exemplo
                          `prof.curseduca.pro,api.sendgrid.com`.
    CARGA_TROCA_MODELOS   reescreve o campo `model` das chamadas aos provedores,
                          `original=substituto,...` — por exemplo
                          `claude-sonnet-5=claude-haiku-4-5,sonar-pro=sonar`.
                          O custo gravado no banco continua com o preço do
                          ORIGINAL: nessa rodada, o custo do banco não vale.
    CARGA_BANCO_PERMITIDO host do banco aceito além dos locais (o do staging).

POR QUE NO TRANSPORTE, E NÃO TROCANDO OS PROVEDORES
O teste quer medir o teto do backend, e parte do teto são os pools do httpx
(`app/core/http_client.py`: 100 conexões para chamadas curtas, 300 para streams,
`pool=5` s). Trocar os provedores por funções falsas tiraria os pools do
caminho. Aqui o transporte real continua, com os MESMOS limites que o cliente
pediu; só o destino (e, se pedido, o modelo) muda. O host original segue em
`x-host-original`, que é o que o servidor falso usa para saber quem imitar.

TRAVA: recusa subir se o banco não for local nem o declarado em
CARGA_BANCO_PERMITIDO. O ambiente de carga roda com APP_ENV=production, então
esta é a única coisa que impede apontar o backend de teste para o banco de verdade.
"""

import json
import os
import sys

_ALVO = os.environ.get("CARGA_FALSO_URL", "")
_TROCAS = dict(
    par.split("=", 1)
    for par in os.environ.get("CARGA_TROCA_MODELOS", "").replace(" ", "").split(",")
    if "=" in par
)

if _ALVO or _TROCAS:
    from urllib.parse import urlparse

    _banco = urlparse(os.environ.get("DATABASE_URL", "").replace("+asyncpg", ""))
    _permitidos = {"localhost", "127.0.0.1", "host.docker.internal"}
    if os.environ.get("CARGA_BANCO_PERMITIDO"):
        _permitidos.add(os.environ["CARGA_BANCO_PERMITIDO"])
    if not (_banco.hostname in _permitidos or (_banco.hostname or "").startswith("m360-carga")):
        sys.stderr.write(
            f"[carga] RECUSADO: DATABASE_URL aponta para '{_banco.hostname}', que não é local "
            "nem o declarado em CARGA_BANCO_PERMITIDO. O interceptador de carga não roda "
            "contra outro banco.\n"
        )
        raise SystemExit(3)

    import httpx

    _destino = httpx.URL(_ALVO) if _ALVO else None
    _HOSTS = {h for h in os.environ.get("CARGA_FALSO_HOSTS", "").replace(" ", "").split(",") if h}
    _NUNCA = {"localhost", "127.0.0.1"} | ({_destino.host} if _destino else set())
    _init_original = httpx.AsyncClient.__init__

    def _vai_para_o_falso(host: str) -> bool:
        if _destino is None or host in _NUNCA:
            return False
        return not _HOSTS or host in _HOSTS

    def _troca_modelo(request: httpx.Request) -> httpx.Request:
        """Devolve uma cópia com o `model` do corpo trocado, ou o próprio pedido."""
        if request.method != "POST" or "json" not in request.headers.get("content-type", ""):
            return request
        try:
            corpo = json.loads(request.content)
        except (ValueError, httpx.RequestNotRead):
            return request
        if not isinstance(corpo, dict) or corpo.get("model") not in _TROCAS:
            return request
        corpo["model"] = _TROCAS[corpo["model"]]
        cabecalhos = [(k, v) for k, v in request.headers.multi_items() if k.lower() != "content-length"]
        return httpx.Request(
            request.method, request.url, headers=cabecalhos,
            content=json.dumps(corpo).encode(), extensions=request.extensions,
        )

    class _Interceptador(httpx.AsyncBaseTransport):
        def __init__(self, interno: httpx.AsyncBaseTransport):
            self._interno = interno

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            host = request.url.host
            if _TROCAS:
                request = _troca_modelo(request)
            if _vai_para_o_falso(host):
                request.url = request.url.copy_with(
                    scheme=_destino.scheme, host=_destino.host, port=_destino.port
                )
                request.headers["host"] = f"{_destino.host}:{_destino.port}"
                request.headers["x-host-original"] = host
            return await self._interno.handle_async_request(request)

        async def aclose(self) -> None:
            await self._interno.aclose()

    def _init(self, *args, **kwargs):
        if kwargs.get("transport") is None:
            limites = kwargs.get("limits") or httpx.Limits(max_connections=100, max_keepalive_connections=20)
            kwargs["transport"] = _Interceptador(httpx.AsyncHTTPTransport(limits=limites))
        _init_original(self, *args, **kwargs)

    httpx.AsyncClient.__init__ = _init
    sys.stderr.write(
        f"[carga] interceptador ativo (pid {os.getpid()}): falso={_ALVO or '-'} "
        f"hosts={','.join(sorted(_HOSTS)) or ('todos' if _ALVO else '-')} trocas={_TROCAS or '-'}\n"
    )
