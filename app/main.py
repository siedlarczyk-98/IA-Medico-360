"""
Médico 360 — Aplicação principal FastAPI.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.limiter import limiter

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
_cors_origins = [settings.frontend_url]
if not settings.is_production:
    # localhost e 127.0.0.1 são tratados como origens distintas pelo browser
    _cors_origins += [
        settings.frontend_url.replace("localhost", "127.0.0.1"),
        settings.frontend_url.replace("127.0.0.1", "localhost"),
    ]
    _cors_origins = list(dict.fromkeys(_cors_origins))  # dedup

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────
app.include_router(api_v1_router)
