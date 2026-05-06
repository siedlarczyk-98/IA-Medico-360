
import httpx
from app.core.config import get_settings
settings = get_settings()

CLASSIFICATION_PROMPT = """Classifique a especialidade médica da pergunta abaixo escolhendo exatamente UMA das opções da lista.

Opções válidas: Cardiologia, Pediatria, Neurologia, Ortopedia, Pneumologia, Gastroenterologia, Endocrinologia, Infectologia, Psiquiatria, Dermatologia, Nefrologia, Ginecologia, Obstetrícia, Urologia, Oftalmologia, Otorrinolaringologia, Hematologia, Reumatologia, Oncologia, Mastologia, Angiologia, Coloproctologia, Alergia e Imunologia, Nutrologia, Radiologia, Medicina de Emergência, Cirurgia, Geriatria, Medicina do Trabalho, Medicina Esportiva, Clínica Geral
Se a pergunta NÃO for de natureza clínica/médica, responda: NAO_CLINICO
Responda APENAS com a especialidade, sem explicação.

Pergunta: {prompt}"""


async def detect_specialty(prompt: str) -> str | None:
    """
    Detecta a especialidade médica do prompt via GPT-5.4 Nano.
    Retorna a especialidade ou None se não for clínico.
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
                    "max_completion_tokens": 20,
                    "temperature": 0,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            specialty = data["choices"][0]["message"]["content"].strip()

            if specialty == "NAO_CLINICO":
                return None

            return specialty

    except Exception:
        return None