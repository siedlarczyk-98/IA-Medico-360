"""
Histórico da conversa lido do banco.

Antes, o histórico usado para montar o prompt vinha do **cliente**, no corpo da
requisição. Duas consequências:

1. Segurança — o servidor mandava ao modelo, e cobrava do usuário, um texto que
   ele mesmo nunca tinha verificado. Um cliente podia afirmar qualquer coisa
   como "dito anteriormente pelo assistente".
2. Correção — o que o médico via na tela e o que o modelo recebia podiam
   divergir (aba antiga, reload no meio, resposta que falhou em gravar).

O banco é a única fonte que o servidor pode conferir, e é a mesma que alimenta
a tela ao reabrir a conversa.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.models import Conversation, Interaction
from app.services.context_budget import Turn

logger = logging.getLogger(__name__)

# Teto de interações lidas do banco antes do corte por tokens. Existe para
# limitar o custo da CONSULTA numa conversa muito longa; quem decide o que
# entra no prompt é o orçamento de tokens, não este número.
MAX_INTERACTIONS_LIDAS = 40


async def load_history(
    db,
    user_id,
    conversation_id,
) -> list[Turn]:
    """
    Turnos anteriores da conversa, do mais antigo para o mais recente.

    Devolve lista vazia quando não há conversa, quando ela é de outro usuário,
    ou quando é a primeira mensagem — os três casos são normais, não erro.
    """
    if not conversation_id:
        return []

    # A checagem de posse é o ponto do exercício: sem ela, passar o id de uma
    # conversa alheia traria o conteúdo dela para dentro do prompt.
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )).scalar_one_or_none()
    if conv is None:
        return []

    result = await db.execute(
        select(Interaction)
        .where(
            Interaction.conversation_id == conv.id,
            # Interações aguardando clarificação não têm resposta ainda, e a
            # `resolved` já foi absorvida pelo prompt consolidado — incluí-las
            # duplicaria a pergunta no contexto.
            Interaction.status == "completed",
        )
        .order_by(Interaction.started_at.desc())
        .limit(MAX_INTERACTIONS_LIDAS)
        .options(selectinload(Interaction.responses))
    )
    interactions = list(result.scalars().all())
    interactions.reverse()

    turns: list[Turn] = []
    for interaction in interactions:
        if interaction.prompt_text:
            turns.append(Turn(role="user", content=interaction.prompt_text))

        # Só a primeira resposta sem erro. O orquestrador grava uma por
        # interação; uma resposta com `error_message` é registro de falha, e
        # devolvê-la ao modelo o faria acreditar que já respondeu aquilo.
        for resp in sorted(interaction.responses, key=lambda r: r.created_at):
            if resp.error_message or not resp.response_text:
                continue
            turns.append(Turn(role="assistant", content=resp.response_text))
            break

    return turns
