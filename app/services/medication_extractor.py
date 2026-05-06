"""
Médico 360 — Extrator de medicamentos via IA.
Preserva o texto original (raw) e normaliza para nome genérico.
Diferencia source: 'prompt' vs 'response'.
"""

import json

import httpx

from app.core.config import get_settings

settings = get_settings()

EXTRACTION_PROMPT = """Extraia TODOS os medicamentos, fármacos e substâncias ativas mencionados no texto abaixo.

Para cada medicamento, retorne:
- "raw": exatamente como aparece no texto (preservar siglas, nomes comerciais, abreviações)
- "normalized": nome genérico por extenso em português, minúsculo

Regras de normalização:
- Siglas devem ser expandidas: "HCTZ" vira "hidroclorotiazida", "AAS" vira "ácido acetilsalicílico", "MTX" vira "metotrexato"
- Nomes comerciais devem virar genérico: "Novalgina" vira "dipirona", "Cozaar" vira "losartana", "Glifage" vira "metformina"
- Sempre minúsculo no normalized
- Sem duplicatas (se aparecer duas vezes, retornar só uma)

Retorne APENAS um JSON array de objetos com campos "raw" e "normalized". Se não houver medicamentos, retorne [].

Texto: {text}"""

async def extract_medications(text: str) -> list[dict]:
    """
    Extrai lista de medicamentos com raw + normalized de um texto.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
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
                    "max_completion_tokens": 300,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            print(f"DEBUG NANO RAW RESPONSE: {content}")
            content = content.replace("```json", "").replace("```", "").strip()

            medications = json.loads(content)
            if isinstance(medications, list):
                return [
                    {
                        "raw": m.get("raw", "").strip(),
                        "normalized": m.get("normalized", "").strip().lower(),
                    }
                    for m in medications
                    if isinstance(m, dict) and m.get("raw")
                ]

            return []

    except Exception as e:
        print(f"DEBUG EXTRACT ERROR: {e}")
        return []


async def extract_from_interaction(
    prompt: str,
    responses: list[str],
) -> list[dict]:
    """
    Extrai medicamentos do prompt e das respostas separadamente.
    Retorna lista de dicts com 'medication_raw', 'medication_normalized' e 'source'.
    """
    results = []
    seen_normalized = set()

    # Extrair do prompt (o que o médico citou)
    prompt_meds = await extract_medications(prompt)
    for med in prompt_meds:
        if med["normalized"] not in seen_normalized:
            results.append({
                "medication_raw": med["raw"],
                "medication_normalized": med["normalized"],
                "source": "prompt",
            })
            seen_normalized.add(med["normalized"])

    # Extrair das respostas (o que a IA sugeriu)
    all_responses = "\n".join(responses)
    response_meds = await extract_medications(all_responses)
    for med in response_meds:
        if med["normalized"] not in seen_normalized:
            results.append({
                "medication_raw": med["raw"],
                "medication_normalized": med["normalized"],
                "source": "response",
            })
            seen_normalized.add(med["normalized"])

    return results