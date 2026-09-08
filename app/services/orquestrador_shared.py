"""
Peças comuns a `/orquestrador/query` e `/orquestrador/stream`.

Os dois serviços nasceram como cópias quase literais um do outro: título de
conversa, resolução de posse da conversa, consolidação de clarificação e
montagem do histórico eram o mesmo código escrito duas vezes. Isso já tinha
cobrado seu preço — `orquestrador_service` importava `_check_clarification`
(privada) de dentro do serviço de streaming, e os mapas de modo já divergiam
entre os arquivos.

Aqui as funções recebem `db` e `user_id` como argumentos em vez de lerem
`self`, que era a única diferença real entre as duas versões.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update

from app.core import circuit_breaker
from app.core.config import get_settings
from app.core.prompts import SYSTEM_PROMPT_CLARIFICATION
from app.models.models import (
    Conversation,
    FileExtraction,
    Interaction,
    InteractionMedication,
    InteractionResponse,
    PubmedValidation,
)
from app.services.context_budget import (
    DEFAULT_HISTORY_TOKEN_BUDGET,
    Turn,
    fit_turns_with_attachment_budget,
    turns_to_messages,
)
from app.services.conversation_history import load_history
from app.services.folder_context_service import contexto_da_pasta, evolucao_da_pasta
from app.services.integracoes.ai_providers import get_provider_by_type
from app.services.integracoes.pubmed_service import validate_with_pubmed
from app.services.medication_extractor import extract_from_interaction
from app.services.orquestrador_modes import (
    MODOS_CACHEAVEIS,
    MODOS_NAO_TRIADOS,
    PHARMA_CHECK_MIN_CONFIDENCE,
    PHARMA_MODES,
    OrquestradorMode,
    upgrade_mode_for_attachments,
)
from app.services.response_metadata import build_metadata_from_cached
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.triage_service import triage

logger = logging.getLogger(__name__)

# Via `get_provider_by_type`, e NÃO `OpenAIProvider()` direto.
#
# Este era o único provider do projeto instanciado fora do registry — e por
# isso o único que escapava do `DlpEnforcingProvider`. O verificador de
# clarificação recebe o histórico da conversa E o bloco de evolução da pasta
# (ver `_prompt_com_contexto`), ou seja, o texto mais sensível do produto: ele
# saía para a OpenAI sem passar pelo DLP.
#
# `tests/test_dlp_enforcement.py` varre o `PROVIDER_TYPE_REGISTRY` e garante
# que todo provider DE LÁ sai embrulhado — mas esta instância nunca entrava no
# registry, então o teste passava com o furo aberto.
_clarification_provider = get_provider_by_type("openai")
_CLARIFICATION_MODEL = "gpt-5.4-nano"


def make_title(prompt: str) -> str:
    """Título da conversa, sem os prefixos que o upload injeta no prompt."""
    if prompt.startswith('[Imagem:'):
        prompt = prompt.split('\n\n', 1)[-1] if '\n\n' in prompt else prompt
    elif '---\n\n' in prompt:
        prompt = prompt.split('---\n\n', 1)[1]
    return prompt[:100] + ('...' if len(prompt) > 100 else '')


async def load_context_messages(
    db,
    user_id: UUID,
    conversation_id: UUID | None,
    budget_tokens: int = DEFAULT_HISTORY_TOKEN_BUDGET,
    *,
    pergunta_atual: str | None = None,
    folder_id: UUID | None = None,
) -> list[dict]:
    """
    Histórico da conversa como lista de turnos, pronta para o provider.

    Substituiu o achatamento em texto (`[Conversa anterior] Médico: ...`) que
    era enviado como uma única mensagem `user`. Duas mudanças:

    - Os papéis viram papéis de verdade. O modelo distinguia quem falou o quê
      por um rótulo dentro do texto, que ele podia ignorar ou confundir com
      conteúdo; agora a distinção é estrutural.
    - O corte é por orçamento de tokens, não por 800 caracteres por mensagem.

    O prompt usado para o cache semântico continua sendo o texto atual sem
    histórico — a separação é deliberada, senão cada conversa teria chave de
    cache própria e o cache nunca acertaria.

    Quando a conversa está numa pasta e `pergunta_atual` é informada, um bloco
    com trechos relevantes das OUTRAS conversas da pasta entra ANTES do
    histórico próprio, como uma fala de contexto identificada.
    """
    turns = await load_history(db, user_id, conversation_id)

    bloco_pasta = ""
    if pergunta_atual:
        bloco_pasta = await contexto_da_pasta(
            db, user_id, conversation_id, pergunta_atual, folder_id=folder_id
        )

    if bloco_pasta:
        # O bloco entra como turno de usuário e ANTES do histórico: é pano de
        # fundo, não a última coisa dita. E ocupa o orçamento junto com o
        # resto — se a conversa própria for longa, ela ganha o espaço, que é o
        # comportamento certo (o caso atual vale mais que casos vizinhos).
        turns = [Turn(role="user", content=bloco_pasta), *turns]

    # Orçamentos separados: o texto de um exame anexado não disputa espaço com
    # a conversa. Ver `context_budget.fit_turns_with_attachment_budget`.
    mensagens = turns_to_messages(fit_turns_with_attachment_budget(turns, budget_tokens))

    # A evolução é acrescentada DEPOIS do corte por orçamento, e é o único
    # bloco que não o disputa.
    #
    # Se ela entrasse junto com os outros turnos, uma conversa longa dentro da
    # pasta acabaria descartando justamente o texto que o médico escreveu para
    # ser sempre considerado — e ele não teria como perceber. O contrato deste
    # campo é "está em toda mensagem desta pasta"; um orçamento que às vezes o
    # remove é outro contrato.
    #
    # O custo é limitado na origem: `MAX_CHARS_EVOLUCAO` recusa textos grandes
    # na API, e `formatar_bloco_evolucao` trunca o que já estiver gravado.
    bloco_evolucao = await evolucao_da_pasta(
        db, user_id, conversation_id, folder_id=folder_id
    )
    if bloco_evolucao:
        mensagens = [{"role": "user", "content": bloco_evolucao}, *mensagens]

    return mensagens


# Marcador de contexto de paciente numa mensagem do histórico montado.
#
# `load_context_messages` devolve uma lista de dicts pronta para o provider, e
# quem chama não tem como saber se ali dentro há material específico de um
# paciente ou só a conversa. Este prefixo é o sinal — os dois blocos que
# carregam dado de paciente (`formatar_bloco` e `formatar_bloco_evolucao`)
# começam com "[", e são os únicos turnos sintéticos da lista.
def pode_usar_cache(mode: str, mensagens: list[dict]) -> bool:
    """Decide se esta pergunta pode ler E gravar no cache semântico.

    Três condições, todas necessárias:

    1. O cache está ligado (`semantic_cache_enabled`). Hoje é `False` — ver o
       comentário da flag em `core/config`: medição mostrou 0 acertos em 240
       interações, e o custo é ~1s por pergunta antes do primeiro token.
    2. O modo é cacheável (`MODOS_CACHEAVEIS`).
    3. O contexto não carrega dado de paciente — ver
       `contexto_tem_dado_de_paciente`.

    Existe como função única porque a decisão precisa ser a MESMA na leitura e
    na gravação, nos dois caminhos do orquestrador. Quatro pontos que poderiam
    divergir passam a ler daqui.
    """
    if not get_settings().semantic_cache_enabled:
        return False
    return mode in MODOS_CACHEAVEIS and not contexto_tem_dado_de_paciente(mensagens)


def contexto_tem_dado_de_paciente(mensagens: list[dict]) -> bool:
    """Diz se o contexto montado carrega material específico de um paciente.

    Serve para decidir CACHEABILIDADE, e é por isso que erra para o lado
    seguro: qualquer bloco injetado conta.

    O problema que isto resolve: a chave do cache semântico é
    `(modo, prompt_sanitizado)` — sem usuário, sem pasta, sem histórico. Mas a
    RESPOSTA é gerada com a evolução do paciente e os trechos da pasta
    injetados. "Qual anti-hipertensivo escolher?" dentro da pasta de um
    paciente com DRC produz uma conduta calibrada para aquela função renal; a
    mesma pergunta de outro médico daria HIT e devolveria aquela conduta.

    São dois danos ao mesmo tempo: vazamento de dado clínico de terceiro, e
    risco clínico direto — uma recomendação derivada de um paciente que não é
    o da pergunta.

    O guardrail de cacheabilidade que já existia não cobre isto: ele avalia
    apenas o TEXTO da pergunta, que por construção não contém o contexto.
    """
    return any(
        m.get("role") == "user" and str(m.get("content", "")).lstrip().startswith("[")
        for m in mensagens
    )


async def ensure_conversation(
    db,
    user_id: UUID,
    conversation_id: UUID | None,
    prompt: str,
    folder_id: UUID | None = None,
) -> UUID:
    """
    Devolve a conversa indicada, se ela pertencer ao usuário; senão cria uma.

    O filtro por `user_id` é o que impede que um id de conversa alheio seja
    adotado — um id que não bate simplesmente cai fora e vira conversa nova.
    """
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv.id

    conv = Conversation(
        user_id=user_id,
        title=make_title(prompt),
        feature="ORQUESTRADOR",
        folder_id=folder_id,
    )
    db.add(conv)
    await db.flush()
    return conv.id


async def resolve_clarification_prompt(
    db,
    user_id: UUID,
    conversation_id: UUID,
    clarification_answers: str,
) -> str:
    """
    Monta o prompt consolidado: pergunta original + perguntas + respostas.

    Sem a interaction pendente, devolve só as respostas — fallback sem perda,
    preferível a falhar e descartar o que o médico acabou de escrever.
    """
    result = await db.execute(
        select(Interaction).where(
            Interaction.conversation_id == conversation_id,
            Interaction.user_id == user_id,
            Interaction.status == "pending_clarification",
        ).order_by(Interaction.started_at.desc()).limit(1)
    )
    pending = result.scalar_one_or_none()

    if not pending:
        return clarification_answers

    questions_text = "\n".join(f"- {q}" for q in (pending.clarification_questions or []))
    consolidated = (
        f"{pending.prompt_text}\n\n"
        f"Informações complementares solicitadas:\n{questions_text}\n\n"
        f"Respostas do médico:\n{clarification_answers}"
    )

    pending.status = "resolved"
    await db.flush()

    return consolidated


async def link_attachments(db, user_id: UUID, interaction_id: UUID, attachment_ids) -> None:
    """
    Carimba os anexos com a mensagem em que foram enviados.

    Sem isto o anexo se perdia: o texto extraído ia embutido no prompt e, ao
    reabrir a conversa, o médico não via mais quais exames tinha mandado.

    O `user_id` entra no UPDATE mesmo já tendo sido checado na resolução dos
    arquivos — uma segunda barreira custa nada aqui e impede que um caminho
    futuro que esqueça a primeira consiga carimbar arquivo alheio.
    """
    if not attachment_ids:
        return

    await db.execute(
        update(FileExtraction)
        .where(
            FileExtraction.id.in_(list(attachment_ids)),
            FileExtraction.user_id == user_id,
        )
        .values(interaction_id=interaction_id)
    )


# Teto do contexto mostrado ao verificador de clarificação. Ele só precisa
# saber SE a informação existe, não lê-la inteira — e roda num modelo pequeno.
MAX_CHARS_CONTEXTO_CLARIFICACAO = 4000


def _prompt_com_contexto(prompt: str, contexto: list[dict] | None) -> str:
    """
    Anexa o contexto disponível à mensagem avaliada.

    Sem isto o verificador julgava a pergunta pelo texto cru e pedia ao médico
    justamente aquilo que o histórico e a pasta já continham — o caso real que
    motivou esta mudança foi "discuta o caso do paciente com os arquivos desta
    pasta" respondido com "qual é a queixa principal do paciente?".
    """
    if not contexto:
        return prompt

    partes = []
    restante = MAX_CHARS_CONTEXTO_CLARIFICACAO
    # De trás para frente: o contexto mais recente é o mais relevante para
    # decidir se a pergunta atual se sustenta.
    for msg in reversed(contexto):
        trecho = (msg.get("content") or "")[:restante]
        if not trecho:
            break
        partes.append(trecho)
        restante -= len(trecho)
        if restante <= 0:
            break

    if not partes:
        return prompt

    return (
        "[Contexto já disponível]\n"
        + "\n---\n".join(reversed(partes))
        + f"\n\n[Mensagem a avaliar]\n{prompt}"
    )


async def check_clarification(prompt: str, contexto: list[dict] | None = None) -> dict:
    """
    Verifica se o caso clínico tem contexto suficiente para valer uma resposta.

    `contexto` são os turnos que o modelo que responde vai receber — histórico
    da conversa e trechos da pasta. O verificador precisa julgar com a MESMA
    informação, senão bloqueia perguntas que já têm resposta no material.

    Falha silenciosa por decisão: se o classificador cair, assumir "suficiente"
    entrega uma resposta talvez rasa; assumir "insuficiente" bloquearia o médico
    com perguntas que ninguém gerou.
    """
    try:
        # Sob o disjuntor das auxiliares: com a OpenAI degradada isto falha na
        # hora em vez de gastar os 8s do timeout, e o `except` abaixo já assume
        # "suficiente" — o mesmo resultado, sem a espera.
        async def _chamar():
            return await _clarification_provider.complete(
                model_id=_CLARIFICATION_MODEL,
                prompt=_prompt_com_contexto(prompt, contexto),
                system_prompt=SYSTEM_PROMPT_CLARIFICATION,
                temperature=0.0,
                timeout=8,
            )

        response = await circuit_breaker.openai_auxiliares.chama(_chamar)
        raw = response.text.strip()
        # Remove possível markdown ```json ... ```
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        logger.warning(f"Clarification check falhou: {e}. Assumindo suficiente.")
        return {"sufficient": True}


# ── Roteamento: decidir qual agente atende ───────────────────────────────────

# Piso de confiança da triagem. Abaixo dele não adivinhamos o agente — pedimos
# ao médico que reformule. Estava escrito como literal `0.7` nos DOIS serviços;
# mudar num não chegava no outro.
CONFIANCA_MINIMA_TRIAGEM = 0.7

# Texto único para o pedido de reformulação. Os dois caminhos diziam coisas
# diferentes na MESMA situação — o `/query` mencionava "para te indicar o agente
# correto" e o `/stream` não. Mesma pergunta, duas respostas, dependendo de o
# frontend ter pedido streaming ou não.
MENSAGEM_PRECISA_REFINAR = (
    "Preciso de um pouco mais de aprofundamento para te indicar o agente correto. "
    "Pode reformular com mais detalhes?"
)


@dataclass(frozen=True)
class DecisaoDeRota:
    """Para onde a pergunta vai — sem saber se a resposta será JSON ou SSE.

    `precisa_refinar` é o único caminho de saída antecipada. Quem chama decide
    COMO comunicar isso (corpo de resposta no `/query`, evento de erro no
    `/stream`); o QUE comunicar é decidido aqui, uma vez só.
    """

    mode: str | None
    confidence: float
    precisa_refinar: bool = False


async def decidir_rota(
    prompt: str, mode: str | None, tem_anexos: bool
) -> DecisaoDeRota:
    """Resolve o modo final a partir do que o frontend pediu e do que a triagem vê.

    As regras, na ordem em que importam:

    1. Anexo promove a raciocínio clínico — quem manda imagem quer leitura de exame.
    2. Modo explícito do frontend dispensa triagem e vale 1.0 de confiança...
    3. ...EXCETO `PHARMA_CHECK`, que ainda passa pela triagem para descobrir o
       sub-modo (bula, receita, genérico, interação). O gate de confiança baixa
       é ignorado nesse caso: o usuário já escolheu o modo.
    4. Confiança abaixo do piso vira pedido de reformulação — MENOS quando há
       anexo, porque aí a informação que falta veio no arquivo, não no texto.
    5. Sub-modos de pharma com confiança insuficiente caem para busca rápida —
       responder bula errada é pior que responder de forma genérica.

    A promoção por anexo acontece DUAS vezes de propósito: antes da triagem,
    para o modo explícito, e de novo depois dela, para o modo que a triagem
    escolheu. Só a primeira existia, e por isso uma mensagem sem modo explícito
    ("e esse aqui?" com um exame junto) escapava — a triagem devolvia
    QUICK_SEARCH e o exame ia para um modelo sem visão.
    """
    mode = upgrade_mode_for_attachments(mode, tem_anexos)
    explicit_pharma = mode == "PHARMA_CHECK"

    if mode and not explicit_pharma:
        return DecisaoDeRota(mode=mode, confidence=1.0)

    resultado = await triage(prompt)
    mode = resultado["mode"]
    confidence = resultado["confidence"]

    # A triagem não pode ESCOLHER um modo que só o médico aciona. O prompt de
    # triagem nem lista DATA_OCEAN, mas um modelo pode devolver o que quiser —
    # e um DATA_OCEAN vindo daqui mandaria uma pergunta clínica comum para um
    # caminho lento e cobrado por uso de ferramenta, sem que ninguém pedisse.
    if mode in MODOS_NAO_TRIADOS:
        mode = OrquestradorMode.QUICK_SEARCH.value

    # A triagem classificou o TEXTO sozinho, sem saber do anexo. Promove de
    # novo com essa informação antes de qualquer gate.
    mode = upgrade_mode_for_attachments(mode, tem_anexos)

    # Com anexo, confiança baixa não é sinal de pergunta mal formulada: é o
    # texto sendo curto porque o conteúdo está no arquivo. Mandar o médico
    # reescrever "e esse aqui?" depois de ele anexar o exame é pedir que ele
    # repita o que já enviou.
    if confidence < CONFIANCA_MINIMA_TRIAGEM and not explicit_pharma and not tem_anexos:
        return DecisaoDeRota(mode=mode, confidence=confidence, precisa_refinar=True)

    if mode == "PHARMA_CHECK" and confidence < PHARMA_CHECK_MIN_CONFIDENCE:
        mode = "CLINICAL_REASONING" if not explicit_pharma else "PHARMA_CHECK"

    if (
        mode in PHARMA_MODES
        and mode != "PHARMA_CHECK"
        and confidence < PHARMA_CHECK_MIN_CONFIDENCE
        and not explicit_pharma
    ):
        mode = "QUICK_SEARCH"

    return DecisaoDeRota(mode=mode, confidence=confidence)


@dataclass
class PosProcessamento:
    """O que o pós-processamento apurou, para quem precisa montar o payload."""

    classification: dict
    medications: list
    pubmed: object


async def pos_processar_interacao(
    db,
    interaction,
    sanitized_prompt: str,
    texto_resposta: str,
    mode: str,
) -> PosProcessamento:
    """
    Roda especialidade, medicamentos e PubMed em paralelo e persiste o resultado.

    Estas ~45 linhas viviam duplicadas em `orquestrador_service` e
    `orquestrador_stream_service`, diferindo apenas na origem do texto da
    resposta. É a forma exata dos quatro bugs de divergência que este projeto
    já teve: alguém corrige um campo de um lado, o outro caminho segue gravando
    dado diferente para a mesma interação, e nada compara os dois.

    O `topic=""` no PubMed é deliberado: usar o próprio texto da resposta como
    fallback de tópico evita esperar a detecção de especialidade para começar,
    e as três chamadas ficam de fato independentes dentro do `gather`.
    """
    classification, medications, pubmed = await asyncio.gather(
        detect_specialty_and_topic(sanitized_prompt),
        extract_from_interaction(sanitized_prompt, [texto_resposta]),
        validate_with_pubmed(agent_response=texto_resposta, mode=mode, topic=""),
    )

    interaction.specialty_detected = classification["specialty"]
    interaction.topic_detected = classification["topic"]
    interaction.confidence_score = pubmed.confidence_score

    for med in medications:
        db.add(InteractionMedication(
            interaction_id=interaction.id,
            medication_raw=med["medication_raw"],
            medication_normalized=med["medication_normalized"],
            source=med["source"],
        ))

    # Citações que o modelo alegou e o PubMed conferiu.
    for c in pubmed.cited_guidelines_verified:
        if c.pmid:
            db.add(PubmedValidation(
                interaction_id=interaction.id,
                pmid=c.pmid,
                article_title=c.title,
                abstract_snippet=None,
                relevance_score=1.0 if c.verified else 0.0,
            ))

    # Diretrizes mais recentes que o corte de treino do modelo.
    for a in pubmed.newer_guidelines_found:
        db.add(PubmedValidation(
            interaction_id=interaction.id,
            pmid=a.pmid,
            article_title=a.article_title,
            abstract_snippet=a.abstract_snippet or None,
            relevance_score=0.0,
        ))

    return PosProcessamento(
        classification=classification,
        medications=medications,
        pubmed=pubmed,
    )


async def registrar_hit_de_cache(
    db,
    *,
    user_id: UUID,
    company_id: UUID | None,
    conversation_id: UUID | None,
    folder_id: UUID | None,
    mode: str,
    sanitized_prompt: str,
    prompt_sanitizado: bool,
    confidence: float,
    cached: dict,
) -> tuple[UUID, Interaction]:
    """
    Grava a resposta vinda do cache no histórico do usuário ATUAL.

    Devolve `(conversation_id, interaction)` para que quem chamou possa
    devolver ids que são DELE — e não os do payload cacheado.

    Dois defeitos que isto veio consertar, e que só existiam porque os dois
    caminhos tinham cópias separadas deste bloco:

    1. O `/query` retornava o dicionário do cache cru. Como o cache é global
       por modo, `conversation_id` e `interaction_id` de lá são da interação
       que o POPULOU — de outro médico. Não havia IDOR (`ensure_conversation`
       filtra por `user_id`), mas o médico ficava com um identificador de outro
       titular e a mensagem saía do histórico dele.
    2. Sem criar a `Interaction`, `cache_hit` nunca era gravado — e
       `vigilancia_service.medir_cache_semantico` conta hits exatamente por
       esse campo. A métrica ficava cega para metade do tráfego.

    Não faz commit: cada caminho tem sua própria política de transação (o
    `/stream` commita aqui, o `/query` deixa para o endpoint).
    """
    conv_id = await ensure_conversation(
        db, user_id, conversation_id, sanitized_prompt, folder_id=folder_id
    )
    interaction = Interaction(
        conversation_id=conv_id,
        user_id=user_id,
        company_id=company_id,
        feature="ORQUESTRADOR",
        mode=mode,
        prompt_text=sanitized_prompt,
        prompt_sanitized=prompt_sanitizado,
        triage_confidence=confidence,
        triage_category=mode,
        cache_hit=True,
        confidence_score=cached.get("confidence_score"),
        specialty_detected=cached.get("specialty_detected"),
        topic_detected=cached.get("topic_detected"),
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(interaction)
    await db.flush()
    db.add(InteractionResponse(
        interaction_id=interaction.id,
        model_used=cached.get("model_used") or "cache",
        response_text=cached.get("response_text") or "",
        cost_usd=Decimal("0"),
        extra_metadata=build_metadata_from_cached(cached),
    ))
    return conv_id, interaction
