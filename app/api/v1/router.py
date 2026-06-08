from fastapi import APIRouter

from app.api.v1.endpoints.agregador import router as agregador_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.orquestrador import router as orquestrador_router
from app.api.v1.endpoints.usage import router as usage_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(agregador_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(orquestrador_router)
api_v1_router.include_router(usage_router, prefix="/users", tags=["usage"])
