"""
Médico 360 — Cache Redis genérico (JSON) para etapas determinísticas.

Usado para memoizar chamadas caras e repetíveis (triage, detecção de
especialidade, lookups PubMed por PMID). Toda falha de Redis é silenciosa:
o caller deve seguir com a chamada real (fallback sem perda).

Conexão única com pool, reaproveitada por todo o processo.
"""

import hashlib
import json
import logging

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# TTLs (segundos)
TTL_TRIAGE = 7200        # 2h
TTL_SPECIALTY = 3600     # 1h
TTL_MEDICATION = 86400   # 24h
TTL_PUBMED = 2592000     # 30 dias

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis


def make_key(namespace: str, *parts: str) -> str:
    """Chave estável: med360:<namespace>:<sha1 das partes>."""
    raw = "||".join(parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"med360:{namespace}:{digest}"


async def get_json(key: str) -> dict | list | None:
    try:
        data = await _get_redis().get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning("Redis get falhou (%s): %s", key, e)
    return None


async def set_json(key: str, value: dict | list, ttl: int) -> None:
    try:
        await _get_redis().setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception as e:
        logger.warning("Redis set falhou (%s): %s", key, e)
