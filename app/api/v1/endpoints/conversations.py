from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Conversation, Interaction, InteractionResponse, User
from app.schemas.conversations import ConversationDetail, ConversationMessage, ConversationSummary

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id, Conversation.status == True)
        .order_by(Conversation.updatedat.desc())
        .limit(100)
    )
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
            Conversation.status == True,
        )
        .options(
            selectinload(Conversation.interactions).selectinload(Interaction.responses)
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")

    messages: list[ConversationMessage] = []
    for interaction in sorted(conv.interactions, key=lambda i: i.started_at):
        messages.append(ConversationMessage(role="user", content=interaction.prompt_text))

        if conv.feature == "AGREGADOR":
            for resp in sorted(interaction.responses, key=lambda r: r.createdat):
                if not resp.error_message:
                    messages.append(ConversationMessage(
                        role="assistant",
                        content=resp.response_text,
                        mode=resp.model_used,
                    ))
        else:
            # ORQUESTRADOR — single response, mode comes from interaction
            for resp in sorted(interaction.responses, key=lambda r: r.createdat):
                if not resp.error_message:
                    messages.append(ConversationMessage(
                        role="assistant",
                        content=resp.response_text,
                        mode=interaction.mode,
                    ))
                    break  # one response per orquestrador interaction

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        feature=conv.feature,
        messages=messages,
        createdat=conv.createdat,
        updatedat=conv.updatedat,
    )
