import json
import logging

from app.core.config import get_settings
from app.core.http_client import get_client
from app.medicina import especialidades
from app.services import cache_service

logger = logging.getLogger(__name__)

settings = get_settings()

NAO_CLINICO = "Cotidiano/Não clínico"

# A lista sai do vocabulário canônico, não é digitada aqui.
#
# Antes eram 31 nomes CURTOS escritos à mão neste arquivo ("Ortopedia",
# "Endocrinologia", "Clínica Geral") — vocabulário INCOMPATÍVEL com o de
# `users.specialty`, que guarda os nomes completos do CFM. O resultado ia para
# `interactions.specialty_detected`, então qualquer análise que cruzasse "a
# especialidade da pergunta" com "a especialidade do médico" comparava grafias
# diferentes da mesma coisa e dava resultado errado sem parecer errado.
#
# Continua sendo um SUBCONJUNTO (`detector=True`): mandar as 55 infla o prompt
# de toda pergunta sem melhorar a classificação.
_OPCOES = ", ".join(especialidades.nomes_para_detector())

CLASSIFICATION_PROMPT = f"""Analise a pergunta abaixo e retorne APENAS um JSON com dois campos:

1. "specialty": escolha exatamente UMA das opções da lista.
Opções válidas: {_OPCOES}
Se a pergunta NÃO for de natureza clínica/médica, use "NAO_CLINICO".

2. "topic": o tema específico da pergunta, normalizado em português (máximo 4 palavras minúsculas). Exemplos de normalização:
   - "PA alta no PS" → "crise hipertensiva"
   - "dose de amox pra sinusite" → "posologia sinusite"
   - "paciente com dor no peito" → "dor torácica aguda"
   - "interação losartana com enalapril" → "interação medicamentosa"
   - "como montar um consultório" → "gestão consultório"

Retorne APENAS o JSON, sem explicação.

Pergunta: {{prompt}}"""  # `{{` escapa a chave: o placeholder é preenchido depois, por .format()


async def detect_specialty_and_topic(prompt: str) -> dict:
    """
    Detecta especialidade e tema da pergunta via GPT-5.4 Nano.
    Retorna dict com 'specialty' e 'topic', ou valores None.
    Determinístico (temp=0) → cacheado no Redis por 1h.
    """
    cache_key = cache_service.make_key("specialty", prompt)
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
                "model": "gpt-5.4-nano",
                "messages": [
                    {"role": "user", "content": CLASSIFICATION_PROMPT.format(prompt=prompt)},
                ],
                "max_completion_tokens": 60,
                "temperature": 0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()

        result = json.loads(content)

        bruto = result.get("specialty", "").strip()
        topic = result.get("topic", "").strip().lower()

        if bruto == "NAO_CLINICO":
            specialty = NAO_CLINICO
        else:
            # Normaliza para o RÓTULO canônico antes de gravar em
            # `interactions.specialty_detected`. O modelo às vezes responde fora
            # da lista (ou com grafia própria) apesar da instrução; sem isto,
            # essa string entraria no banco como se fosse vocabulário nosso.
            slug = especialidades.normalizar(bruto)
            specialty = especialidades.nome_de(slug) if slug else None
            if bruto and slug is None:
                logger.warning("Especialidade fora do vocabulário na classificação: %r", bruto)

        out = {
            "specialty": specialty or None,
            "topic": topic or None,
        }
        await cache_service.set_json(cache_key, out, cache_service.TTL_SPECIALTY)
        return out

    except Exception as e:
        logger.warning(f"Specialty detection failed: {e}")
        return {"specialty": None, "topic": None}