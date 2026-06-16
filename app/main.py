"""
Médico 360 — Aplicação principal FastAPI.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter

logger = logging.getLogger(__name__)

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core import http_client

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown hooks."""
    # Startup
    print(f"🚀 Médico 360 iniciando [{settings.app_env}]")
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
_cors_origins = [settings.frontend_url] + settings.embed_allowed_origins
if not settings.is_production:
    # localhost e 127.0.0.1 são tratados como origens distintas pelo browser
    _cors_origins += [
        settings.frontend_url.replace("localhost", "127.0.0.1"),
        settings.frontend_url.replace("127.0.0.1", "localhost"),
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
