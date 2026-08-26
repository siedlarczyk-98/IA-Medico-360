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
from uuid import UUID

from sqlalchemy import select

from app.core.prompts import SYSTEM_PROMPT_CLARIFICATION
from app.models.models import Conversation, Interaction
from app.services.ai_providers import OpenAIProvider

logger = logging.getLogger(__name__)

# Janela de histórico enviada ao modelo. São MENSAGENS, não turnos — dez
# mensagens são cinco idas e voltas.
HISTORY_WINDOW = 10
# Corte por mensagem, em caracteres. É uma aproximação grosseira de orçamento
# de contexto; a Fase 4 do plano a substitui por contagem de tokens.
HISTORY_CHARS_PER_MESSAGE = 800

_clarification_provider = OpenAIProvider()
_CLARIFICATION_MODEL = "gpt-5.4-nano"


def make_title(prompt: str) -> str:
    """Título da conversa, sem os prefixos que o upload injeta no prompt."""
    if prompt.startswith('[Imagem:'):
        prompt = prompt.split('\n\n', 1)[-1] if '\n\n' in prompt else prompt
    elif '---\n\n' in prompt:
        prompt = prompt.split('---\n\n', 1)[1]
    return prompt[:100] + ('...' if len(prompt) > 100 else '')


def build_enriched_prompt(sanitized_prompt: str, history) -> str:
    """
    Achata o histórico num único prompt de usuário.

    O prompt de cache continua sendo o `sanitized_prompt` sem histórico — a
    separação é deliberada, senão cada conversa teria chave de cache própria e
    o cache nunca acertaria.
    """
    if not history:
        return sanitized_prompt

    parts = ["[Conversa anterior]"]
    for msg in history[-HISTORY_WINDOW:]:
        role_label = "Médico" if msg.role == "user" else "Assistente"
        parts.append(f"{role_label}: {msg.content[:HISTORY_CHARS_PER_MESSAGE]}")
    parts.append("[Pergunta atual]")
    return "\n".join(parts) + f"\nMédico: {sanitized_prompt}"


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


async def check_clarification(prompt: str) -> dict:
    """
    Verifica se o caso clínico tem contexto suficiente para valer uma resposta.

    Falha silenciosa por decisão: se o classificador cair, assumir "suficiente"
    entrega uma resposta talvez rasa; assumir "insuficiente" bloquearia o médico
    com perguntas que ninguém gerou.
    """
    try:
        response = await _clarification_provider.complete(
            model_id=_CLARIFICATION_MODEL,
            prompt=prompt,
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
