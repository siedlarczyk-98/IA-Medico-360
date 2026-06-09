"""
Médico 360 — Cache Semântico via PostgreSQL + pgvector.

Pipeline por query:
  1. Guardrail + normalização (GPT-4o-mini): verifica se o prompt é cacheável
     e expande siglas médicas (PAC→pneumonia adquirida na comunidade, ICFEr→...).
  2. Embedding do prompt normalizado (text-embedding-3-small, 1536 dims).
  3. Busca cosine similarity no pgvector (threshold 0.92).
  4. HIT → retorna resposta cacheada; MISS → retorna None + dados para store futuro.

Modos:
  - QUICK_SEARCH: sempre cacheável (se guardrail passar)
  - CLINICAL_REASONING: cacheável apenas se sem dados de paciente específico
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http_client import get_client
from app.services import cache_service

logger = logging.getLogger(__name__)
settings = get_settings()

SIMILARITY_THRESHOLD = 0.92
TTL_DAYS = 30
TTL_EXACT_SECONDS = 30 * 24 * 3600  # fast-path exato no Redis: 30 dias
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536


def _exact_key(mode: str, raw_prompt: str) -> str:
    return cache_service.make_key("semcache_exact", mode, raw_prompt.strip())


# ── Guardrail + Normalização ──────────────────────────────────

async def _normalize_prompt(
    client: httpx.AsyncClient,
    mode: str,
    prompt: str,
) -> tuple[bool, str]:
    """
    Retorna (cacheable, normalized_prompt).
    Usa GPT-4o-mini para:
    1. Decidir se o prompt é genérico (cacheável) ou específico de paciente.
    2. Expandir siglas médicas e padronizar vocabulário.
    """
    clinical_reasoning_extra = (
        " For CLINICAL_REASONING mode, be strict: any patient-specific data "
        "(age, sex, lab values, specific doses, temporal references like 'há 3 dias', "
        "'meu paciente', specific exam findings) makes it NOT cacheable."
        if mode == "CLINICAL_REASONING"
        else ""
    )

    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        timeout=10,
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 200,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a medical query classifier and normalizer. "
                        "Given a medical query in Portuguese, determine if it is a generic medical question "
                        "(cacheable) or contains patient-specific data (not cacheable). "
                        "Generic questions ask about medications, dosages, guidelines, or clinical concepts "
                        "without specific patient data. "
                        "Also expand Brazilian medical abbreviations: "
                        "PAC=pneumonia adquirida na comunidade, IC=insuficiência cardíaca, "
                        "ICFEr=insuficiência cardíaca com fração de ejeção reduzida, "
                        "HAS=hipertensão arterial sistêmica, DM=diabetes mellitus, "
                        "DRC=doença renal crônica, DPOC=doença pulmonar obstrutiva crônica, "
                        "IAM=infarto agudo do miocárdio, AVC=acidente vascular cerebral, "
                        "FA=fibrilação atrial, TEP=tromboembolismo pulmonar, TVP=trombose venosa profunda."
                        + clinical_reasoning_extra
                        + " Return JSON only: "
                        '{"cacheable": true/false, "normalized_prompt": "expanded query in Portuguese"}'
                    ),
                },
                {"role": "user", "content": prompt[:1000]},
            ],
        },
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"] or "{}"
    try:
        data = json.loads(content)
        return bool(data.get("cacheable", False)), data.get("normalized_prompt", prompt)
    except (json.JSONDecodeError, KeyError):
        return False, prompt


# ── Embedding ─────────────────────────────────────────────────

async def _embed(client: httpx.AsyncClient, text_: str) -> list[float]:
    resp = await client.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={"model": EMBEDDING_MODEL, "input": text_[:8000]},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


# ── pgvector lookup ───────────────────────────────────────────

async def _lookup(
    db: AsyncSession,
    mode: str,
    embedding: list[float],
) -> dict | None:
    """Busca hit por cosine similarity. Retorna response_json ou None."""
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
    now = datetime.now(timezone.utc)

    try:
        result = await db.execute(
            text(
                "SELECT id, response_json, "
                "1 - (prompt_embedding <=> CAST(:emb AS vector)) AS sim "
                "FROM semantic_cache "
                "WHERE mode = :mode AND expires_at > :now "
                "ORDER BY prompt_embedding <=> CAST(:emb AS vector) "
                "LIMIT 1"
            ),
            {"emb": vector_str, "mode": mode, "now": now},
        )
        row = result.fetchone()
        if row and row.sim >= SIMILARITY_THRESHOLD:
            # Incrementa o contador de hits e persiste imediatamente — o caller
            # pode retornar (cache HIT) antes do commit final do pipeline.
            await db.execute(
                text("UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = :id"),
                {"id": row.id},
            )
            await db.commit()
            return row.response_json
    except Exception as exc:
        logger.warning("[Cache] Erro no lookup pgvector: %s", exc)
        await db.rollback()
    return None


# ── API pública ───────────────────────────────────────────────

async def get_cached_response(
    db: AsyncSession,
    mode: str,
    prompt: str,
) -> tuple[dict, str, list] | None:
    """
    Retorna (response_dict, normalized_prompt, embedding) se HIT,
    ou None se MISS. Em caso de MISS, normalized_prompt e embedding
    são retornados via store_response separadamente — mas aqui retornamos
    None para sinalizar MISS ao caller.

    Na prática, o caller deve capturar normalized_prompt e embedding
    mesmo no MISS para poder chamar store_response depois.
    Portanto, essa função retorna sempre a tupla:
      - hit=True: (response_dict, normalized_prompt, embedding)
      - hit=False: (None, normalized_prompt, embedding)
    """
    # Fast-path: match exato do prompt cru no Redis evita 2 chamadas OpenAI
    # (normalização + embedding) e a busca vetorial para prompts repetidos.
    try:
        exact = await cache_service.get_json(_exact_key(mode, prompt))
        if exact is not None:
            logger.debug("[Cache] HIT exato (Redis fast-path)")
            return exact, "", []
    except Exception:
        pass

    try:
        client = get_client()
        cacheable, normalized = await _normalize_prompt(client, mode, prompt)
        if not cacheable:
            logger.debug("[Cache] Prompt não cacheável (dados específicos de paciente)")
            return None, normalized, []

        embedding = await _embed(client, normalized)

        cached = await _lookup(db, mode, embedding)
        if cached is not None:
            logger.debug("[Cache] HIT — retornando resposta cacheada")
            # popula o fast-path para o próximo prompt idêntico
            await cache_service.set_json(_exact_key(mode, prompt), cached, TTL_EXACT_SECONDS)
            return cached, normalized, embedding

        logger.debug("[Cache] MISS — sem match acima do threshold")
        return None, normalized, embedding

    except Exception as exc:
        logger.warning("[Cache] Erro no lookup, seguindo sem cache: %s", exc)
        return None, "", []


async def store_response(
    db: AsyncSession,
    mode: str,
    normalized_prompt: str,
    embedding: list[float],
    response_dict: dict,
    raw_prompt: str | None = None,
) -> None:
    """Persiste a resposta no cache com TTL de 30 dias."""
    if not embedding or not normalized_prompt:
        return
    # popula o fast-path exato para o prompt cru desta interação
    if raw_prompt:
        await cache_service.set_json(_exact_key(mode, raw_prompt), response_dict, TTL_EXACT_SECONDS)
    try:
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=TTL_DAYS)

        async with db.begin_nested():
            await db.execute(
                text(
                    "INSERT INTO semantic_cache "
                    "(id, mode, normalized_prompt, prompt_embedding, response_json, hit_count, created_at, expires_at) "
                    "VALUES (gen_random_uuid(), :mode, :norm, CAST(:emb AS vector), :resp, 0, :now, :exp) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "mode": mode,
                    "norm": normalized_prompt,
                    "emb": vector_str,
                    "resp": json.dumps(response_dict),
                    "now": now,
                    "exp": expires,
                },
            )
        logger.debug("[Cache] Resposta armazenada (modo=%s)", mode)
    except Exception as exc:
        logger.warning("[Cache] Erro ao armazenar resposta: %s", exc)
