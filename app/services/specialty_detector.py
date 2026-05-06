import json
import httpx
from app.core.config import get_settings

settings = get_settings()

CLASSIFICATION_PROMPT = """Analise a pergunta abaixo e retorne APENAS um JSON com dois campos:

1. "specialty": escolha exatamente UMA das opções da lista.
Opções válidas: Cardiologia, Pediatria, Neurologia, Ortopedia, Pneumologia, Gastroenterologia, Endocrinologia, Infectologia, Psiquiatria, Dermatologia, Nefrologia, Ginecologia, Obstetrícia, Urologia, Oftalmologia, Otorrinolaringologia, Hematologia, Reumatologia, Oncologia, Mastologia, Angiologia, Coloproctologia, Alergia e Imunologia, Nutrologia, Radiologia, Medicina de Emergência, Cirurgia, Geriatria, Medicina do Trabalho, Medicina Esportiva, Clínica Geral
Se a pergunta NÃO for de natureza clínica/médica, use "NAO_CLINICO".

2. "topic": o tema específico da pergunta, normalizado em português (máximo 4 palavras minúsculas). Exemplos de normalização:
   - "PA alta no PS" → "crise hipertensiva"
   - "dose de amox pra sinusite" → "posologia sinusite"
   - "paciente com dor no peito" → "dor torácica aguda"
   - "interação losartana com enalapril" → "interação medicamentosa"
   - "como montar um consultório" → "gestão consultório"

Retorne APENAS o JSON, sem explicação.

Pergunta: {prompt}"""


async def detect_specialty_and_topic(prompt: str) -> dict:
    """
    Detecta especialidade e tema da pergunta via GPT-5.4 Nano.
    Retorna dict com 'specialty' e 'topic', ou valores None.
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
                        {"role": "user", "content": CLASSIFICATION_PROMPT.format(prompt=prompt)},
                    ],
                    "max_completion_tokens": 60,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            content = content.replace("```json", "").replace("```", "").strip()

            result = json.loads(content)

            specialty = result.get("specialty", "").strip()
            topic = result.get("topic", "").strip().lower()

            if specialty == "NAO_CLINICO":
                specialty = "Cotidiano/Não clínico"

            return {
                "specialty": specialty or None,
                "topic": topic or None,
            }

    except Exception:
        return {"specialty": None, "topic": None}