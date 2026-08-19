"""
Health checks.

Dois endpoints com propósitos distintos — a diferença importa para o
orquestrador da plataforma:

  /health       liveness  — o processo está de pé? Nunca toca dependência.
                            Falhar aqui significa "reinicie o container".
  /health/ready readiness — dá para atender requisição? Verifica Postgres e
                            Redis. Falhar aqui significa "pare de mandar
                            tráfego", não "reinicie".

Antes existia só o primeiro, respondendo "healthy" com o banco fora do ar.
"""

import asyncio
import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.database import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Curto de propósito: o health check não pode ficar pendurado atrás da mesma
# indisponibilidade que deveria estar reportando.
_TIMEOUT_SEGUNDOS = 3.0


@router.get("/health")
async def liveness():
    """O processo responde. Não consulta dependência — ver docstring do módulo."""
    return {"status": "healthy", "service": "medico360"}


async def _checa_postgres() -> None:
    async with async_session_factory() as sessao:
        await sessao.execute(text("SELECT 1"))


async def _checa_redis() -> None:
    from app.services.cache_service import _get_redis

    await _get_redis().ping()


async def _resultado(nome: str, verificacao) -> tuple[str, bool, str | None]:
    try:
        await asyncio.wait_for(verificacao(), timeout=_TIMEOUT_SEGUNDOS)
        return nome, True, None
    except TimeoutError:
        return nome, False, "timeout"
    except Exception as e:
        # A mensagem vai para o log, não para a resposta: string de conexão e
        # topologia interna não podem vazar num endpoint público.
        logger.warning("Health check de %s falhou: %s", nome, e)
        return nome, False, type(e).__name__


@router.get("/health/ready")
async def readiness(response: Response):
    """503 se qualquer dependência essencial estiver indisponível."""
    checagens = await asyncio.gather(
        _resultado("postgres", _checa_postgres),
        _resultado("redis", _checa_redis),
    )

    dependencias = {nome: {"ok": ok, "erro": erro} for nome, ok, erro in checagens}
    tudo_ok = all(ok for _, ok, _ in checagens)

    if not tudo_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if tudo_ok else "degraded",
        "dependencies": dependencias,
    }
