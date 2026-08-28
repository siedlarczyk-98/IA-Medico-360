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
    # Discussão de exames anexados (laudo em PDF, imagem, laboratorial em
    # documento). Exige modelo com visão — ver MODES_REQUIRING_VISION.
    EXAM_REVIEW = "EXAM_REVIEW"
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

# Modos que consultam o cache semântico. Estava escrito como literal em
# `orquestrador_service` e `orquestrador_stream_service` — as duas cópias que
# este módulo existe para evitar —, e agora também é lido pela vigilância, que
# mede a taxa de acerto do cache. Se a medição usasse a própria lista, ela
# poderia continuar dizendo "o cache está saudável" depois de alguém mudar
# quais modos o consultam.
#
# `EXAM_REVIEW` fica de fora de propósito: a pergunta vem acompanhada de um
# exame específico de um paciente, e nada ali é reaproveitável entre usuários.
MODOS_CACHEAVEIS: frozenset[str] = frozenset({
    OrquestradorMode.QUICK_SEARCH,
    OrquestradorMode.CLINICAL_REASONING,
})

# Threshold mínimo de confiança para acionar o PharmaDB.
PHARMA_CHECK_MIN_CONFIDENCE = 0.90

# Modos atendidos por PharmaDB (sem LLM) mapeiam para None: o roteamento por
# modelo não se aplica a eles.
MODE_MODEL_MAP: dict[str, str | None] = {
    OrquestradorMode.QUICK_SEARCH: "sonar-pro",
    OrquestradorMode.CLINICAL_REASONING: "claude-sonnet-4-6",
    OrquestradorMode.PRODUCTIVITY: "gpt-5.4-nano",
    OrquestradorMode.EXAM_REVIEW: "claude-sonnet-4-6",
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
    # Leitura de exame é descrição de achados, não geração criativa.
    OrquestradorMode.EXAM_REVIEW: 0.0,
}

# Modos que só funcionam com um modelo capaz de ver a imagem. Rotear um deles
# para Perplexity, por exemplo, entregaria ao médico uma discussão de exame
# baseada só na descrição textual gerada por outro modelo — sem que ele saiba.
MODES_REQUIRING_VISION: frozenset[str] = frozenset({OrquestradorMode.EXAM_REVIEW})

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
    # Todos com visão — cair num modelo cego aqui devolveria uma leitura de
    # exame feita sem o exame.
    OrquestradorMode.EXAM_REVIEW: ["gpt-4o", "gemini-2.5-flash"],
}

def upgrade_mode_for_attachments(mode: str | None, tem_anexos: bool) -> str | None:
    """
    Promove CLINICAL_REASONING para EXAM_REVIEW quando há exame anexado.

    Por que não deixar a triagem escolher EXAM_REVIEW: ela só vê o TEXTO da
    pergunta e não sabe se veio anexo. "O que você acha disso?" com uma
    tomografia junto e a mesma frase sem anexo pedem modos diferentes, e a
    triagem não tem como distinguir.

    Por que só a partir de CLINICAL_REASONING: anexar um documento e pedir
    "resuma isto" é PRODUCTIVITY, e continua sendo. A promoção só acontece
    quando a pergunta já era de raciocínio clínico — aí o anexo é o exame que
    se quer discutir.

    Um modo explícito vindo da interface nunca é promovido: se o médico
    escolheu, ele mandou.
    """
    if not tem_anexos:
        return mode
    if mode == OrquestradorMode.CLINICAL_REASONING:
        return OrquestradorMode.EXAM_REVIEW.value
    return mode


# Resposta do atalho de saudação. Constante porque `/query` e `/stream`
# precisam devolver exatamente a mesma coisa.
GREETING_REPLY = (
    "Olá! Sou o assistente do Médico 360. Pode me perguntar sobre posologia, "
    "protocolos, interações medicamentosas ou descrever um caso clínico que eu ajudo."
)
