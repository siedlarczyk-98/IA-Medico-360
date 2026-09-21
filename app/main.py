"""
Médico 360 — Aplicação principal FastAPI.
"""

import json
import logging
import sys
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter

# Windows console usa cp1252 por padrão, que não suporta emoji — força UTF-8
# no stdout/stderr para evitar UnicodeEncodeError em prints do startup/reload.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logger = logging.getLogger(__name__)

from app.api.v1.router import api_v1_router
from app.calculators.formulas import load_all_formulas
from app.core import http_client
from app.core.body_limit import LimiteDeCorpoMiddleware
from app.core.config import get_settings, origens_confiaveis
from app.core.error_tracking import setup_sentry
from app.core.lider import como_lider
from app.core.logging_config import RequestIdMiddleware, setup_logging
from app.core.security_headers import CabecalhosDeSegurancaMiddleware
from app.core.telemetry import setup_phoenix
from app.middleware import ner
from app.services import expurgo_agendado, news_agendado, vigilancia_agendada

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown hooks."""
    # `AsyncExitStack` porque a liderança é um context manager que precisa durar
    # toda a vida da aplicação: a conexão aberta é o que sustenta o advisory lock.
    async with AsyncExitStack() as pilha:
        # Startup — logging primeiro, para o resto do boot já sair estruturado.
        setup_logging(level=settings.log_level, json_output=settings.is_production)
        logger.info("Médico 360 iniciando", extra={"env": settings.app_env})
        if setup_sentry(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release=settings.sentry_release or None,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        ):
            logger.info(
                "Sentry ativo (scrubbing de PII habilitado, amostragem de traces em %.0f%%)",
                settings.sentry_traces_sample_rate * 100,
            )
        setup_phoenix(
            api_key=settings.phoenix_api_key,
            project_name=settings.phoenix_project_name,
            endpoint=settings.phoenix_endpoint,
        )
        await http_client.startup()
        # Carrega o modelo de NER do DLP fora do caminho da 1ª requisição (~1s).
        if not ner.warmup():
            logger.warning("NER do DLP indisponível — nomes sem palavra-gatilho não serão mascarados")
        # Popula o registry de formulas no boot: um formula_key ausente falha
        # aqui, e nao na primeira execucao clinica em producao.
        load_all_formulas()
        # Expurgo de retenção (LGPD art. 16) roda dentro do processo, e não por cron
        # externo: o agendamento no painel do Railway parou sem avisar e ficou 39
        # dias sem ninguém saber. Ver app/services/expurgo_agendado.py.
        #
        # OS TRÊS SÓ SOBEM NO PROCESSO LÍDER. Cada worker do uvicorn roda este
        # `lifespan` inteiro; sem a eleição, N workers = N cópias de cada agendador.
        # O expurgo é idempotente, mas a vigilância alarmaria N vezes (o silêncio de
        # 24h por tag é um dict em memória, por processo) e o pipeline de notícias
        # chamaria o modelo N vezes. Ver `app/core/lider.py`.
        lideranca = await pilha.enter_async_context(como_lider("agendadores"))
        tarefa_expurgo = expurgo_agendado.iniciar() if lideranca else None
        # Vigilancia: pergunta a cada 6h se as garantias silenciosas do
        # sistema continuam valendo (cache gravando, custo estavel, expurgo
        # rodando). O cache semantico ficou meses desligado porque o dado existia
        # e ninguem consultava. Ver app/services/vigilancia_agendada.py.
        tarefa_vigilancia = vigilancia_agendada.iniciar() if lideranca else None
        # Pipeline de noticias no processo, e nao num Cron Job do painel: o modulo
        # veio de um repo onde ele era exatamente isso, e este projeto ja perdeu 39
        # dias de expurgo com um agendador que parou sem avisar.
        tarefa_noticias = news_agendado.iniciar() if lideranca else None
        yield
        # Shutdown
        await news_agendado.parar(tarefa_noticias)
        await vigilancia_agendada.parar(tarefa_vigilancia)
        await expurgo_agendado.parar(tarefa_expurgo)
        await http_client.shutdown()
        logger.info("Médico 360 encerrando")


app = FastAPI(
    title="Médico 360",
    description="Plataforma de Assistência Clínica com IA — API Backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# ── Rate Limiting ────────────────────────────────────────────
app.state.limiter = limiter


def _limite_de_requisicoes_excedido(request: Request, exc: RateLimitExceeded):
    """429 do slowapi com uma frase que o usuário entende.

    O handler padrão responde `{"error": "Rate limit exceeded: 60 per 1 minute"}`
    — em inglês, numa chave que nenhum cliente nosso lê. Todos os apps mostram o
    `detail`, que é onde o FastAPI põe as mensagens; sem ele o médico via "Erro
    ao conectar com o servidor" ao bater num limite.

    Reaproveita o handler original para não perder os cabeçalhos `Retry-After` e
    `X-RateLimit-*` que ele injeta, e mantém `error` para quem já o lia.
    """
    resposta = _rate_limit_exceeded_handler(request, exc)
    resposta.body = json.dumps(
        {
            "detail": "Muitas requisições em pouco tempo. Aguarde um instante e tente de novo.",
            "error": f"Rate limit exceeded: {exc.detail}",
        },
        ensure_ascii=False,
    ).encode()
    resposta.headers["content-length"] = str(len(resposta.body))
    return resposta


app.add_exception_handler(RateLimitExceeded, _limite_de_requisicoes_excedido)

# ── CORS ─────────────────────────────────────────────────────
# UMA lista só, a mesma da guarda anti-CSRF. Eram duas, montadas em lugares
# diferentes, e divergiram: o `dea_url` estava no CORS e fora da guarda, então o
# preflight passava e o POST levava 403. Ver o docstring de `origens_confiaveis`.
_cors_origins = origens_confiaveis(settings)

# Registrado PRIMEIRO = roda por dentro de todos os outros. É de propósito: o 413
# dele precisa atravessar o CORS na volta, senão o navegador esconde o corpo da
# resposta e o app não consegue mostrar a mensagem.
app.add_middleware(LimiteDeCorpoMiddleware)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# Registrado por último = executa primeiro: o request_id precisa existir antes
# de qualquer outro middleware poder falhar.
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    # Sem `max_age` o Starlette manda 600s, e o browser refaz o preflight OPTIONS
    # a cada 10 minutos para CADA rota — uma ida e volta a mais antes de toda
    # chamada com `Authorization`. 24h é o teto que o Firefox respeita; o Chrome
    # limita a 2h por conta própria.
    max_age=86400,
)

# Registrado DEPOIS do CORS = roda por fora dele. Precisa ser assim: é este que
# retira o `Access-Control-Allow-Credentials` que o CORS acabou de pôr, para as
# origens que não autenticam. Ver `security_headers`.
app.add_middleware(CabecalhosDeSegurancaMiddleware, settings=settings)


# ── Exception handler global ─────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Loga o erro internamente e devolve mensagem genérica (sem stack trace)."""
    logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor."},
    )


# ── Routes ───────────────────────────────────────────────────
app.include_router(api_v1_router)
