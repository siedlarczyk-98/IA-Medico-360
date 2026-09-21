"""
Cabeçalhos de segurança da API e credenciais de CORS só para quem autentica.

## Credenciais seletivas

O `CORSMiddleware` tem UM `allow_credentials` para todas as origens. Com ele
ligado, o DEA e as páginas de captação — públicos, sem login, e que nunca mandam
cookie — recebiam `Access-Control-Allow-Credentials: true` como os apps
autenticados. Na prática: um XSS numa dessas páginas faria, do navegador do médico
logado, chamadas COM o cookie de sessão e LERIA a resposta — o histórico clínico
inteiro. A página menos protegida do conjunto virava a porta para a mais sensível.

Este middleware roda por FORA do CORS e retira o cabeçalho quando a origem está
em `origens_sem_credenciais()`. Sem ele o navegador se recusa a entregar ao script
a resposta de uma requisição feita com cookie — que é o bloqueio que se quer.

A origem do LMS parceiro (`embed_allowed_origins`) continua COM credenciais: não
foi possível confirmar se a página deles chama a API diretamente, e tirar às cegas
quebraria o embed. Fica como está até alguém confirmar.

## Cabeçalhos

A API só devolve JSON e SSE; nada dela deveria ser renderizado, emoldurado ou
guardado em cache. Os cabeçalhos abaixo dizem isso ao navegador. `Cache-Control`
só entra quando a rota não definiu o seu (o stream define `no-cache`).

ASGI puro, não `BaseHTTPMiddleware`, para não interferir no streaming.
"""

from app.core.config import Settings

CAMINHOS_DA_DOCUMENTACAO = ("/docs", "/redoc", "/openapi.json")


def origens_sem_credenciais(settings: Settings) -> frozenset[str]:
    """Origens nossas que NÃO autenticam: nunca precisam ler resposta feita com cookie."""
    origens = {settings.dea_url, *settings.landing_pages_origins}
    if not settings.is_production:
        for o in list(origens):
            origens |= {o.replace("localhost", "127.0.0.1"), o.replace("127.0.0.1", "localhost")}
    return frozenset(o for o in origens if o)


class CabecalhosDeSegurancaMiddleware:
    def __init__(self, app, settings: Settings):
        self.app = app
        self.sem_credenciais = origens_sem_credenciais(settings)
        self.hsts = settings.is_production

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origem = dict(scope["headers"]).get(b"origin", b"").decode("latin-1")
        tira_credenciais = origem in self.sem_credenciais
        e_documentacao = scope["path"].startswith(CAMINHOS_DA_DOCUMENTACAO)

        async def enviar(mensagem):
            if mensagem["type"] == "http.response.start":
                cabecalhos = [
                    (k, v) for k, v in mensagem.get("headers", [])
                    if not (tira_credenciais and k.lower() == b"access-control-allow-credentials")
                ]
                presentes = {k.lower() for k, _ in cabecalhos}

                def por(nome: bytes, valor: bytes) -> None:
                    if nome not in presentes:
                        cabecalhos.append((nome, valor))

                por(b"x-content-type-options", b"nosniff")
                por(b"referrer-policy", b"no-referrer")
                por(b"x-frame-options", b"DENY")
                por(b"cache-control", b"no-store")
                if not e_documentacao:
                    # O Swagger carrega script e CSS de CDN; em produção ele nem existe.
                    por(b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                if self.hsts:
                    por(b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                mensagem = {**mensagem, "headers": cabecalhos}
            await send(mensagem)

        await self.app(scope, receive, enviar)
