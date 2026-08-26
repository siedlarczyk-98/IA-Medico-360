"""
Modos do Orquestrador — definição única.

Antes isto vivia replicado em quatro lugares: `triage_service` (VALID_MODES),
`orquestrador_service` e `orquestrador_stream_service` (um jogo de mapas cada) e
`core/prompts` (um terceiro mapa modo→prompt). Acrescentar um modo exigia achar
os quatro, e esquecer um deles falhava em runtime, não no import.

`ModeEnum` em `app/models/models.py` NÃO é isto: aquele é resíduo do ERD
original (BIZU, SHERLOCK, FARMACIA...), com valores que nunca corresponderam aos
modos reais e que nenhum código do orquestrador lê. Foi deixado onde está —
mexer nele é mudança de schema, não de serviço.
"""

from enum import StrEnum


class OrquestradorMode(StrEnum):
    """Modos que a triagem pode devolver e que a API aceita explicitamente."""

    QUICK_SEARCH = "QUICK_SEARCH"
    CLINICAL_REASONING = "CLINICAL_REASONING"
    PHARMA_CHECK = "PHARMA_CHECK"
    PHARMA_BULA = "PHARMA_BULA"
    PHARMA_RECEITA = "PHARMA_RECEITA"
    PHARMA_GENERICO = "PHARMA_GENERICO"
    PRODUCTIVITY = "PRODUCTIVITY"
    # Saudação / mensagem sem conteúdo clínico. Atendido por atalho local,
    # sem gastar chamada de modelo.
    OFF_TOPIC = "OFF_TOPIC"


VALID_MODES: frozenset[str] = frozenset(m.value for m in OrquestradorMode)

PHARMA_MODES: frozenset[str] = frozenset({
    OrquestradorMode.PHARMA_CHECK,
    OrquestradorMode.PHARMA_BULA,
    OrquestradorMode.PHARMA_RECEITA,
    OrquestradorMode.PHARMA_GENERICO,
})

# Threshold mínimo de confiança para acionar o PharmaDB.
PHARMA_CHECK_MIN_CONFIDENCE = 0.90

# Modos atendidos por PharmaDB (sem LLM) mapeiam para None: o roteamento por
# modelo não se aplica a eles.
MODE_MODEL_MAP: dict[str, str | None] = {
    OrquestradorMode.QUICK_SEARCH: "sonar-pro",
    OrquestradorMode.CLINICAL_REASONING: "claude-sonnet-4-6",
    OrquestradorMode.PRODUCTIVITY: "gpt-5.4-nano",
    OrquestradorMode.PHARMA_CHECK: None,
    OrquestradorMode.PHARMA_BULA: None,
    OrquestradorMode.PHARMA_RECEITA: None,
    OrquestradorMode.PHARMA_GENERICO: None,
    OrquestradorMode.OFF_TOPIC: None,
}

# temperature=0 para modos clínicos garante respostas consistentes e reproduzíveis
MODE_TEMPERATURE_MAP: dict[str, float] = {
    OrquestradorMode.QUICK_SEARCH: 0.0,
    OrquestradorMode.CLINICAL_REASONING: 0.0,
    OrquestradorMode.PRODUCTIVITY: 0.7,
}

# Efeito real do toggle Rápido/Detalhado: limita o tamanho da resposta,
# o que reduz tanto o tempo de geração quanto o custo em tokens de saída.
EFFORT_MAX_TOKENS: dict[str, int] = {
    "rápido": 700,
    "detalhado": 4096,
}

# Cadeia de fallback por modo, usada quando o provider primário falha.
FALLBACK_MODELS: dict[str, list[str]] = {
    OrquestradorMode.QUICK_SEARCH: ["gemini-2.5-flash"],
    OrquestradorMode.CLINICAL_REASONING: ["gpt-4o", "gemini-2.5-flash"],
    OrquestradorMode.PRODUCTIVITY: ["gemini-2.5-flash"],
}

# Resposta do atalho de saudação. Constante porque `/query` e `/stream`
# precisam devolver exatamente a mesma coisa.
GREETING_REPLY = (
    "Olá! Sou o assistente do Médico 360. Pode me perguntar sobre posologia, "
    "protocolos, interações medicamentosas ou descrever um caso clínico que eu ajudo."
)
