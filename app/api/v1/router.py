"""Médico 360 — Router principal da API v1."""

from fastapi import APIRouter

from app.api.v1.endpoints.agregador import router as agregador_router
from app.api.v1.endpoints.health import router as health_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(agregador_router)
