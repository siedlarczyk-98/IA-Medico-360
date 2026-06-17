"""
Médico 360 — Extrator de medicamentos via IA.
Preserva o texto original (raw) e normaliza para nome genérico.
Diferencia source: 'prompt' vs 'response'.
"""

import json
import logging

from app.core.config import get_settings
from app.core.http_client import get_client
from app.services import cache_service

settings = get_settings()
logger = logging.getLogger(__name__)

# Extração em UMA única chamada: o texto vem rotulado em duas seções
# (PROMPT e RESPOSTA) e o modelo marca a origem de cada medicamento,
# evitando duas chamadas LLM separadas por interação.
EXTRACTION_PROMPT = """Extraia TODOS os medicamentos, fármacos e substâncias ativas mencionados no texto abaixo.

O texto está dividido em duas seções rotuladas: [PROMPT] (o que o médico escreveu) e [RESPOSTA] (o que a IA respondeu).

Para cada medicamento, retorne:
- "raw": exatamente como aparece no texto (preservar siglas, nomes comerciais, abreviações)
- "normalized": nome genérico por extenso em português, minúsculo
- "source": "prompt" se apareceu na seção [PROMPT], senão "response"

Regras de normalização:
- Siglas devem ser expandidas: "HCTZ" vira "hidroclorotiazida", "AAS" vira "ácido acetilsalicílico", "MTX" vira "metotrexato"
- Nomes comerciais devem virar genérico: "Novalgina" vira "dipirona", "Cozaar" vira "losartana", "Glifage" vira "metformina"
- Sempre minúsculo no normalized
- Sem duplicatas por "normalized": se o mesmo fármaco aparecer no PROMPT e na RESPOSTA, retorne só uma vez com source "prompt"

Retorne APENAS um JSON array de objetos com campos "raw", "normalized" e "source". Se não houver medicamentos, retorne [].

{text}"""


SINGLE_EXTRACTION_PROMPT = """Extraia TODOS os medicamentos, fármacos e substâncias ativas mencionados no texto abaixo.

Para cada medicamento, retorne:
- "raw": exatamente como aparece no texto (preservar siglas, nomes comerciais, abreviações)
- "normalized": nome genérico por extenso em português, minúsculo

Regras de normalização:
- Siglas devem ser expandidas: "HCTZ" vira "hidroclorotiazida", "AAS" vira "ácido acetilsalicílico", "MTX" vira "metotrexato"
- Nomes comerciais devem virar genérico: "Novalgina" vira "dipirona", "Cozaar" vira "losartana", "Glifage" vira "metformina"
- Sempre minúsculo no normalized
- Sem duplicatas

Retorne APENAS um JSON array de objetos com campos "raw" e "normalized". Se não houver medicamentos, retorne [].

Texto: {text}"""


async def extract_medications(text: str) -> list[dict]:
    """
    Extrai lista de medicamentos (raw + normalized) de um único texto.
    Usado pelo fluxo PHARMA_CHECK, que só precisa dos fármacos do prompt.
    Determinístico (temp=0) → cacheado no Redis por 24h.
    """
    cache_key = cache_service.make_key("medication:single", text)
    cached = await cache_service.get_json(cache_key)
    if cached is not None:
        return cached

    try:
        client = get_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-5.4-mini",
                "messages": [
                    {"role": "user", "content": SINGLE_EXTRACTION_PROMPT.format(text=text)},
                ],
                "max_completion_tokens": 300,
                "temperature": 0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()

        medications = json.loads(content)
        if isinstance(medications, list):
            result = [
                {
                    "raw": m.get("raw", "").strip(),
                    "normalized": m.get("normalized", "").strip().lower(),
                }
                for m in medications
                if isinstance(m, dict) and m.get("raw")
            ]
            await cache_service.set_json(cache_key, result, cache_service.TTL_MEDICATION)
            return result
        return []
    except Exception as e:
        logger.warning("Falha ao extrair medicamentos (single): %s", e)
        return []


async def extract_from_interaction(
    prompt: str,
    responses: list[str],
) -> list[dict]:
    """
    Extrai medicamentos do prompt e das respostas em uma única chamada LLM.
    Retorna lista de dicts com 'medication_raw', 'medication_normalized' e 'source'.
    Determinístico (temp=0) → cacheado no Redis por 24h.
    """
    all_responses = "\n".join(responses)
    text = f"[PROMPT]\n{prompt}\n\n[RESPOSTA]\n{all_responses}"

    cache_key = cache_service.make_key("medication:interaction", text)
    cached = await cache_service.get_json(cache_key)
    if cached is not None:
        return cached

    try:
        client = get_client()
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-5.4-mini",
                "messages": [
                    {"role": "user", "content": EXTRACTION_PROMPT.format(text=text)},
                ],
                "max_completion_tokens": 400,
                "temperature": 0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()

        medications = json.loads(content)
        if not isinstance(medications, list):
            return []

        results = []
        seen_normalized = set()
        for m in medications:
            if not isinstance(m, dict) or not m.get("raw"):
                continue
            normalized = m.get("normalized", "").strip().lower()
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            source = m.get("source", "response").strip().lower()
            if source not in {"prompt", "response"}:
                source = "response"
            results.append({
                "medication_raw": m["raw"].strip(),
                "medication_normalized": normalized,
                "source": source,
            })
        await cache_service.set_json(cache_key, results, cache_service.TTL_MEDICATION)
        return results

    except Exception as e:
        logger.warning("Falha ao extrair medicamentos (interaction): %s", e)
        return []