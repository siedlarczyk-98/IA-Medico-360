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


# Um segundo é muito para o Redis (que responde em menos de 1 ms na mesma rede)
# e pouco para o médico: é o máximo que uma requisição aceita perder com cache.
REDIS_TIMEOUT_S = 1.0
REDIS_MAX_CONEXOES = 50


def novo_cliente_redis(url: str | None = None) -> redis.Redis:
    """Cliente Redis com pool BLOQUEANTE e timeouts. O único jeito de criar um.

    Eram dois pools de 20 conexões (este e um dentro do PharmaDB), sem timeout
    nenhum, e os dois defeitos apareciam juntos sob carga:

    - Pool comum CHEIO levanta `ConnectionError` na hora. Como toda falha de Redis
      aqui é silenciosa, o erro virava cache miss — e cache miss na triagem é uma
      chamada paga ao modelo. Carga alta = custo extra, sem aviso. O pool
      bloqueante espera até `timeout` por uma conexão antes de desistir.
    - Sem `socket_timeout`, um Redis travado (não caído: TRAVADO) prendia toda
      requisição indefinidamente, porque o cache está no caminho de todas.

    Continua falhando ABERTO: passado o timeout, quem chama trata como miss.
    """
    pool = redis.BlockingConnectionPool.from_url(
        url or settings.redis_url,
        decode_responses=True,
        max_connections=REDIS_MAX_CONEXOES,
        timeout=REDIS_TIMEOUT_S,
        socket_timeout=REDIS_TIMEOUT_S,
        socket_connect_timeout=REDIS_TIMEOUT_S,
    )
    return redis.Redis(connection_pool=pool)


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = novo_cliente_redis()
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


async def rate_limit_exceeded(key: str, limit: int, window_seconds: int) -> bool:
    """Contador de janela fixa: True quando `key` já passou de `limit` na janela.

    Complementa o rate limit por IP do slowapi para chaves que só existem no corpo
    do request (e-mail). Falha aberta se o Redis cair — o limite por IP continua
    valendo e derrubar o login inteiro por indisponibilidade de cache seria pior.
    """
    try:
        r = _get_redis()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window_seconds)
        return count > limit
    except Exception as e:
        logger.warning("Redis rate limit falhou (%s): %s", key, e)
        return False
