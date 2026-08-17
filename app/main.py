"""
Médico 360 — Aplicação principal FastAPI.
"""

import logging
import sys
from contextlib import asynccontextmanager

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
from app.core.config import get_settings
from app.core import http_client
from app.core.telemetry import setup_phoenix

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown hooks."""
    # Startup
    print(f"🚀 Médico 360 iniciando [{settings.app_env}]")
    setup_phoenix(
        api_key=settings.phoenix_api_key,
        project_name=settings.phoenix_project_name,
        endpoint=settings.phoenix_endpoint,
    )
    await http_client.startup()
    yield
    # Shutdown
    await http_client.shutdown()
    print("🛑 Médico 360 encerrando")


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
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────
_app_origins = [settings.frontend_url, settings.calculadoras_url]
_cors_origins = _app_origins + settings.embed_allowed_origins
if not settings.is_production:
    # localhost e 127.0.0.1 são tratados como origens distintas pelo browser
    for _o in _app_origins:
        _cors_origins += [
            _o.replace("localhost", "127.0.0.1"),
            _o.replace("127.0.0.1", "localhost"),
        ]
_cors_origins = list(dict.fromkeys(_cors_origins))  # dedup

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


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
