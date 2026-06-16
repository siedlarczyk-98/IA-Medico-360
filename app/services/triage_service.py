
import json
import logging

from app.core.config import get_settings
from app.core.http_client import get_client
from app.services import cache_service

logger = logging.getLogger(__name__)

settings = get_settings()

TRIAGE_PROMPT = """Você é o sistema de triagem da plataforma Médico 360. Classifique a pergunta do médico em EXATAMENTE uma categoria.

Categorias:
- QUICK_SEARCH: dúvida direta e objetiva — CID, conduta rápida, doses, protocolos simples, efeitos adversos ou contraindicações gerais de um único medicamento
- CLINICAL_REASONING: caso clínico, diagnóstico diferencial, quadro atípico, discussão complexa, múltiplos sintomas, análise de exames
- PHARMA_CHECK: EXCLUSIVAMENTE checagem de interação medicamentosa direta entre DOIS OU MAIS medicamentos explicitamente nomeados. A pergunta deve citar dois ou mais nomes de medicamentos sendo COMPARADOS ou COMBINADOS. NÃO use para dúvida sobre um único fármaco.
- PHARMA_BULA: pedido de bula, indicações, contraindicações, posologia ou reações adversas de UM medicamento específico nomeado. Exemplos: "bula do Dorflex", "indicações do paracetamol", "o que é contraindicado no Rivotril".
- PHARMA_RECEITA: dúvida sobre receituário, tipo de receita, retenção, Portaria 344 ou dispensação de UM medicamento nomeado. Exemplos: "Rivotril precisa de receita?", "qual receita para codeína", "posso vender clonazepam sem retenção?".
- PHARMA_GENERICO: busca de genérico, similar intercambiável ou comparação de preço de UM medicamento nomeado. Exemplos: "tem genérico do Tylenol?", "similar mais barato para Crestor", "intercambiável do Rivotril".
- PRODUCTIVITY: tarefas não clínicas — gerar email, resumir prontuário, redigir laudo, gestão, finanças, carreira

Retorne APENAS um JSON com dois campos:
- "mode": a categoria escolhida (uma das 7 acima)
- "confidence": número de 0 a 1 indicando sua confiança na classificação

Exemplos — PHARMA_CHECK:
- "Posso dar losartana com espironolactona?" → {{"mode": "PHARMA_CHECK", "confidence": 0.97}}
- "Tem interação entre metformina e glibenclamida?" → {{"mode": "PHARMA_CHECK", "confidence": 0.96}}
- "Warfarina interage com AAS?" → {{"mode": "PHARMA_CHECK", "confidence": 0.96}}

Exemplos — PHARMA_BULA:
- "Bula do Dorflex" → {{"mode": "PHARMA_BULA", "confidence": 0.97}}
- "Quais as indicações do paracetamol?" → {{"mode": "PHARMA_BULA", "confidence": 0.95}}
- "Posologia do Rivotril" → {{"mode": "PHARMA_BULA", "confidence": 0.95}}
- "Contraindicações do omeprazol" → {{"mode": "PHARMA_BULA", "confidence": 0.94}}

Exemplos — PHARMA_RECEITA:
- "Rivotril precisa de receita azul?" → {{"mode": "PHARMA_RECEITA", "confidence": 0.97}}
- "Qual receita para dispensar codeína?" → {{"mode": "PHARMA_RECEITA", "confidence": 0.96}}
- "Clonazepam tem retenção de receita?" → {{"mode": "PHARMA_RECEITA", "confidence": 0.95}}

Exemplos — PHARMA_GENERICO:
- "Tem genérico do Tylenol?" → {{"mode": "PHARMA_GENERICO", "confidence": 0.97}}
- "Similar mais barato para o Crestor" → {{"mode": "PHARMA_GENERICO", "confidence": 0.96}}
- "Intercambiável do Rivotril" → {{"mode": "PHARMA_GENERICO", "confidence": 0.95}}

Exemplos — outros:
- "Quais as contraindicações do metoprolol?" → {{"mode": "QUICK_SEARCH", "confidence": 0.94}}
- "Qual a dose de amoxicilina pra sinusite?" → {{"mode": "QUICK_SEARCH", "confidence": 0.95}}
- "Paciente 60 anos, diabético, com dor torácica e dispneia. ECG com supra de ST em V1-V4" → {{"mode": "CLINICAL_REASONING", "confidence": 0.98}}
- "Me ajuda a montar um cronograma de atividades físicas" → {{"mode": "PRODUCTIVITY", "confidence": 0.90}}

Pergunta: {prompt}"""

VALID_MODES = {
    "QUICK_SEARCH",
    "CLINICAL_REASONING",
    "PHARMA_CHECK",
    "PHARMA_BULA",
    "PHARMA_RECEITA",
    "PHARMA_GENERICO",
    "PRODUCTIVITY",
}

PHARMA_MODES = {"PHARMA_CHECK", "PHARMA_BULA", "PHARMA_RECEITA", "PHARMA_GENERICO"}

# Threshold mínimo de confiança para acionar o PharmaDB.
PHARMA_CHECK_MIN_CONFIDENCE = 0.90


async def triage(prompt: str) -> dict:
    """
    Classifica a pergunta do médico via GPT-5.4 Nano.
    Retorna dict com 'mode' e 'confidence'.
    Determinístico (temp=0) → cacheado no Redis por 2h. Fallback: QUICK_SEARCH.
    """
    cache_key = cache_service.make_key("triage", prompt)
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
                    {"role": "user", "content": TRIAGE_PROMPT.format(prompt=prompt)},
                ],
                "max_completion_tokens": 30,
                "temperature": 0,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()

        result = json.loads(content)
        mode = result.get("mode", "").strip().upper()
        confidence = float(result.get("confidence", 0))

        if mode not in VALID_MODES:
            mode = "QUICK_SEARCH"
            confidence = 0.5

        out = {"mode": mode, "confidence": confidence}
        await cache_service.set_json(cache_key, out, cache_service.TTL_TRIAGE)
        return out

    except Exception as e:
        logger.warning(f"Triage falhou, usando fallback QUICK_SEARCH: {e}")
        return {
            "mode": "QUICK_SEARCH",
            "confidence": 0.0,
        }