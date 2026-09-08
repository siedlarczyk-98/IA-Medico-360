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
    # Consulta a bases de dados públicas brasileiras (DATASUS, CNES, ANVISA,
    # InfoDengue, IBGE...) via ferramenta Data Ocean da Maritaca. NÃO é
    # escolhido pela triagem: o médico o seleciona na interface — ver
    # `decidir_rota` e o comentário em MODOS_NAO_TRIADOS.
    DATA_OCEAN = "DATA_OCEAN"
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
# `DATA_OCEAN` também fica de fora, por motivo diferente do EXAM_REVIEW: as
# respostas dele são reaproveitáveis entre usuários, mas não ENTRE DIAS. Um
# alerta epidemiológico, o número de leitos livres ou a cobertura vacinal
# mudam; servir do cache entregaria um número velho com cara de atual, que é
# pior do que não ter o recurso — o médico não teria como perceber.
MODOS_CACHEAVEIS: frozenset[str] = frozenset({
    OrquestradorMode.QUICK_SEARCH,
    OrquestradorMode.CLINICAL_REASONING,
})

# Modos que a TRIAGEM nunca deve devolver — só chegam por escolha explícita
# do médico na interface.
#
# `DATA_OCEAN` está aqui porque é lento (fluxo agêntico de dezenas de segundos)
# e cobrado por uso de ferramenta. Deixar a triagem escolhê-lo significaria
# mandar uma pergunta clínica comum para um caminho caro e demorado por causa
# de uma classificação errada — e a triagem lê só o texto, sem contexto: ela
# já erra com mensagens curtas (foi o que motivou a correção do EXAM_REVIEW).
# Quando o médico escolhe, ele sabe o que está pedindo e a espera se justifica.
#
# A defesa real está em `decidir_rota`, que descarta o modo se a triagem o
# devolver mesmo assim; esta lista é o registro de QUAIS modos têm essa regra.
MODOS_NAO_TRIADOS: frozenset[str] = frozenset({OrquestradorMode.DATA_OCEAN})

# Threshold mínimo de confiança para acionar o PharmaDB.
PHARMA_CHECK_MIN_CONFIDENCE = 0.90

# Modos atendidos por PharmaDB (sem LLM) mapeiam para None: o roteamento por
# modelo não se aplica a eles.
MODE_MODEL_MAP: dict[str, str | None] = {
    OrquestradorMode.QUICK_SEARCH: "sonar-pro",
    OrquestradorMode.CLINICAL_REASONING: "claude-sonnet-4-6",
    OrquestradorMode.PRODUCTIVITY: "gpt-5.4-nano",
    OrquestradorMode.EXAM_REVIEW: "claude-sonnet-4-6",
    # `sabia-4-thinking`: a ferramenta Data Ocean só existe nos modelos
    # `sabia-4*` (a API devolve 400 nos demais), e a variante `thinking` é a
    # que raciocina sobre quais bases cruzar.
    OrquestradorMode.DATA_OCEAN: "sabia-4-thinking",
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
    # Resposta ancorada em números consultados na hora: não há o que inventar.
    OrquestradorMode.DATA_OCEAN: 0.0,
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
# `DATA_OCEAN` NÃO tem fallback, e a ausência é a decisão.
#
# Nenhum outro modelo consulta as bases brasileiras: cair para o Claude ou o
# GPT devolveria uma resposta plausível, fluente e SEM DADO NENHUM — construída
# da memória de treino, com números possivelmente inventados, no lugar de uma
# consulta ao DATASUS. O médico veria uma resposta com a mesma aparência da
# verdadeira. Falhar visivelmente é melhor.
FALLBACK_MODELS: dict[str, list[str]] = {
    OrquestradorMode.QUICK_SEARCH: ["gemini-2.5-flash"],
    OrquestradorMode.CLINICAL_REASONING: ["gpt-4o", "gemini-2.5-flash"],
    OrquestradorMode.PRODUCTIVITY: ["gemini-2.5-flash"],
    # Todos com visão — cair num modelo cego aqui devolveria uma leitura de
    # exame feita sem o exame.
    OrquestradorMode.EXAM_REVIEW: ["gpt-4o", "gemini-2.5-flash"],
}

# Modos que um anexo promove a EXAM_REVIEW. `QUICK_SEARCH` está aqui porque é
# o que a triagem devolve para "e esse aqui?" — texto curto que só faz sentido
# junto do exame anexado — e roteá-lo mandaria o exame a um modelo cego.
_MODOS_PROMOVIVEIS_POR_ANEXO: frozenset[str] = frozenset({
    OrquestradorMode.CLINICAL_REASONING,
    OrquestradorMode.QUICK_SEARCH,
})


def upgrade_mode_for_attachments(mode: str | None, tem_anexos: bool) -> str | None:
    """
    Promove CLINICAL_REASONING para EXAM_REVIEW quando há exame anexado.

    Por que não deixar a triagem escolher EXAM_REVIEW: ela só vê o TEXTO da
    pergunta e não sabe se veio anexo. "O que você acha disso?" com uma
    tomografia junto e a mesma frase sem anexo pedem modos diferentes, e a
    triagem não tem como distinguir.

    Por que não a partir de PRODUCTIVITY: anexar um documento e pedir "resuma
    isto" é produtividade, e continua sendo. O mesmo vale para os modos de
    pharma, onde o anexo costuma ser uma receita a transcrever, não um exame.

    QUICK_SEARCH TAMBÉM promove, e este é o caso que mais aparece na prática.
    No meio de uma discussão, o médico anexa um exame e escreve "e esse aqui?".
    A triagem lê quatro palavras sem ver o anexo, classifica como busca rápida
    — e QUICK_SEARCH roteia para um modelo SEM VISÃO (`sonar-pro`). O exame
    nunca chegava ao modelo, que respondia com confiança sobre um exame que o
    médico via na tela e ele não. Um anexo somado a uma pergunta curta não é
    busca rápida: é leitura de exame com a pergunta encurtada pelo contexto.

    Um modo explícito vindo da interface nunca é promovido: se o médico
    escolheu, ele mandou.
    """
    if not tem_anexos:
        return mode
    if mode in _MODOS_PROMOVIVEIS_POR_ANEXO:
        return OrquestradorMode.EXAM_REVIEW.value
    return mode


# Resposta do atalho de saudação. Constante porque `/query` e `/stream`
# precisam devolver exatamente a mesma coisa.
GREETING_REPLY = (
    "Olá! Sou o assistente do Médico 360. Pode me perguntar sobre posologia, "
    "protocolos, interações medicamentosas ou descrever um caso clínico que eu ajudo."
)
