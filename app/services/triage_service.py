

import json
import httpx
from app.core.config import get_settings

settings = get_settings()

TRIAGE_PROMPT = """Você é o sistema de triagem da plataforma Médico 360. Classifique a pergunta do médico em EXATAMENTE uma categoria.

Categorias:
- QUICK_SEARCH: dúvida direta e objetiva — posologia, CID, conduta rápida, bulas, doses, protocolos simples, efeitos adversos ou contraindicações de um único medicamento isolado
- CLINICAL_REASONING: caso clínico, diagnóstico diferencial, quadro atípico, discussão complexa, múltiplos sintomas, análise de exames
- PHARMA_CHECK: EXCLUSIVAMENTE checagem de interação medicamentosa direta entre DOIS OU MAIS medicamentos explicitamente nomeados na pergunta, OU contraindicação explícita entre dois ou mais fármacos nomeados. OBRIGATÓRIO: a pergunta deve citar dois ou mais nomes de medicamentos sendo COMPARADOS ou COMBINADOS entre si. NÃO use PHARMA_CHECK para: dúvidas sobre um único fármaco, mecanismo de ação, posologia, efeitos adversos isolados ou contraindicações gerais de um medicamento.
- PRODUCTIVITY: tarefas não clínicas — gerar email, resumir prontuário, redigir laudo, gestão, finanças, carreira

Retorne APENAS um JSON com dois campos:
- "mode": a categoria escolhida (uma das 4 acima)
- "confidence": número de 0 a 1 indicando sua confiança na classificação

Exemplos — PHARMA_CHECK (correto):
- "Posso dar losartana com espironolactona?" → {{"mode": "PHARMA_CHECK", "confidence": 0.97}}
- "Tem interação entre metformina e glibenclamida?" → {{"mode": "PHARMA_CHECK", "confidence": 0.96}}
- "Warfarina interage com AAS? É seguro combinar?" → {{"mode": "PHARMA_CHECK", "confidence": 0.96}}
- "Posso usar amiodarona junto com metoprolol no mesmo paciente?" → {{"mode": "PHARMA_CHECK", "confidence": 0.95}}

Exemplos — NÃO é PHARMA_CHECK:
- "Quais as contraindicações do metoprolol?" → {{"mode": "QUICK_SEARCH", "confidence": 0.94}}
- "Efeitos adversos do paracetamol em dose alta?" → {{"mode": "QUICK_SEARCH", "confidence": 0.94}}
- "Como funciona o mecanismo da varfarina?" → {{"mode": "QUICK_SEARCH", "confidence": 0.93}}
- "Qual a dose de amoxicilina pra sinusite?" → {{"mode": "QUICK_SEARCH", "confidence": 0.95}}
- "Paciente 60 anos, diabético, com dor torácica e dispneia. ECG com supra de ST em V1-V4" → {{"mode": "CLINICAL_REASONING", "confidence": 0.98}}
- "Me ajuda a montar um cronograma de atividades físicas que se encaixe na minha rotina?" → {{"mode": "PRODUCTIVITY", "confidence": 0.90}}

Pergunta: {prompt}"""

VALID_MODES = {"QUICK_SEARCH", "CLINICAL_REASONING", "PHARMA_CHECK", "PRODUCTIVITY"}

# Threshold mínimo de confiança para acionar o PharmaDB.
# Perguntas classificadas como PHARMA_CHECK abaixo deste valor são rebaixadas
# para CLINICAL_REASONING para evitar acionamentos incorretos do serviço externo.
PHARMA_CHECK_MIN_CONFIDENCE = 0.90


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