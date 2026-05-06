
import json
import httpx
from app.core.config import get_settings

settings = get_settings()

EXTRACTION_PROMPT = """Extraia TODOS os medicamentos, fármacos e substâncias ativas mencionados no texto abaixo.

Retorne APENAS um JSON array com os nomes genéricos em português. Se não houver medicamentos, retorne [].

Exemplos de retorno:
["amoxicilina", "dipirona", "enalapril"]
[]

Não inclua classes farmacológicas (ex: "antibiótico", "AINE"), apenas nomes de substâncias específicas.

Texto: {text}"""

async def extract_medications(text: str) -> list[str]:
    """
    Extrai lista de medicamentos de um texto via GPT-5.4 Nano.
    Retorna lista de nomes genéricos ou lista vazia.
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
                    "model": "gpt-5.4-nano",
                    "messages": [
                        {"role": "user", "content": EXTRACTION_PROMPT.format(text=text)},
                    ],
                    "max_completion_tokens": 200,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Limpar possíveis markdown fences
            content = content.replace("```json", "").replace("```", "").strip()

            medications = json.loads(content)
            if isinstance(medications, list):
                return [m.strip().lower() for m in medications if isinstance(m, str)]

            return []

    except Exception:
        return []


async def extract_from_interaction(
    prompt: str,
    responses: list[str],
) -> list[dict]:
    """
    Extrai medicamentos do prompt e das respostas separadamente.
    Retorna lista de dicts com 'medication_name' e 'source'.
    """
    results = []
    seen = set()

    # Extrair do prompt (o que o médico citou)
    prompt_meds = await extract_medications(prompt)
    for med in prompt_meds:
        if med not in seen:
            results.append({"medication_name": med, "source": "prompt"})
            seen.add(med)

    # Extrair das respostas (o que a IA sugeriu)
    all_responses = "\n".join(responses)
    response_meds = await extract_medications(all_responses)
    for med in response_meds:
        if med not in seen:
            results.append({"medication_name": med, "source": "response"})
            seen.add(med)

    return results