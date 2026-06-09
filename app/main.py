"""
Médico 360 — Aplicação principal FastAPI.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ───────────────────────────────────────────────────
app.include_router(api_v1_router)
