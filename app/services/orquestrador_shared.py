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

import json
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, update

from app.core.prompts import SYSTEM_PROMPT_CLARIFICATION
from app.models.models import Conversation, FileExtraction, Interaction
from app.services.context_budget import (
    DEFAULT_HISTORY_TOKEN_BUDGET,
    Turn,
    fit_turns_to_budget,
    turns_to_messages,
)
from app.services.conversation_history import load_history
from app.services.folder_context_service import contexto_da_pasta
from app.services.integracoes.ai_providers import OpenAIProvider
from app.services.orquestrador_modes import (
    PHARMA_CHECK_MIN_CONFIDENCE,
    PHARMA_MODES,
    upgrade_mode_for_attachments,
)
from app.services.triage_service import triage

logger = logging.getLogger(__name__)

_clarification_provider = OpenAIProvider()
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

    return turns_to_messages(fit_turns_to_budget(turns, budget_tokens))


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
        response = await _clarification_provider.complete(
            model_id=_CLARIFICATION_MODEL,
            prompt=_prompt_com_contexto(prompt, contexto),
            system_prompt=SYSTEM_PROMPT_CLARIFICATION,
            temperature=0.0,
            timeout=8,
        )
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
    4. Confiança abaixo do piso vira pedido de reformulação.
    5. Sub-modos de pharma com confiança insuficiente caem para busca rápida —
       responder bula errada é pior que responder de forma genérica.
    """
    mode = upgrade_mode_for_attachments(mode, tem_anexos)
    explicit_pharma = mode == "PHARMA_CHECK"

    if mode and not explicit_pharma:
        return DecisaoDeRota(mode=mode, confidence=1.0)

    resultado = await triage(prompt)
    mode = resultado["mode"]
    confidence = resultado["confidence"]

    if confidence < CONFIANCA_MINIMA_TRIAGEM and not explicit_pharma:
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
