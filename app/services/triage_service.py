

import json
import httpx
from app.core.config import get_settings

settings = get_settings()

TRIAGE_PROMPT = """Você é o sistema de triagem da plataforma Médico 360. Classifique a pergunta do médico em EXATAMENTE uma categoria.

Categorias:
- QUICK_SEARCH: dúvida direta e objetiva — posologia, CID, conduta rápida, bulas, doses, protocolos simples
- CLINICAL_REASONING: caso clínico, diagnóstico diferencial, quadro atípico, discussão complexa, múltiplos sintomas, análise de exames
- PHARMA_CHECK: interações medicamentosas, checagem de risco entre fármacos, contraindicações entre medicamentos específicos
- PRODUCTIVITY: tarefas não clínicas — gerar email, resumir prontuário, redigir laudo, gestão, finanças, carreira

Retorne APENAS um JSON com dois campos:
- "mode": a categoria escolhida (uma das 4 acima)
- "confidence": número de 0 a 1 indicando sua confiança na classificação

Exemplos:
- "Qual a dose de amoxicilina pra sinusite?" → {{"mode": "QUICK_SEARCH", "confidence": 0.95}}
- "Paciente 60 anos, diabético, com dor torácica e dispneia. ECG com supra de ST em V1-V4" → {{"mode": "CLINICAL_REASONING", "confidence": 0.98}}
- "Posso dar losartana com espironolactona?" → {{"mode": "PHARMA_CHECK", "confidence": 0.92}}
- "Me ajuda a montar um cronograma de atividades físicas que se encaixe na minha rotina?" → {{"mode": "PRODUCTIVITY", "confidence": 0.90}}

Pergunta: {prompt}"""

VALID_MODES = {"QUICK_SEARCH", "CLINICAL_REASONING", "PHARMA_CHECK", "PRODUCTIVITY"}


async def triage(prompt: str) -> dict:
    """
    Classifica a pergunta do médico via GPT-5.4 Nano.
    Retorna dict com 'mode' e 'confidence'.
    Timeout: 3 segundos. Fallback: QUICK_SEARCH.
    """
    try:
        async with httpx.AsyncClient(timeout=6) as client:
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

            return {
                "mode": mode,
                "confidence": confidence,
            }

    except Exception as e:
        print(f"Error occurred while triaging: {e}")
        return {
            "mode": "QUICK_SEARCH",
            "confidence": 0.0,
        }