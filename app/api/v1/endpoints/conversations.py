from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.models import Conversation, Interaction, User
from app.schemas.conversations import ConversationDetail, ConversationMessage, ConversationSummary
from app.services.response_metadata import read_response_metadata

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
@limiter.limit("60/minute")
async def list_conversations(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id, Conversation.status.is_(True))
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationDetail)
@limiter.limit("60/minute")
async def get_conversation(
    request: Request,
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    conv_result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
            Conversation.status.is_(True),
        )
    )
    conv = conv_result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversa não encontrada")

    interactions_result = await db.execute(
        select(Interaction)
        .where(Interaction.conversation_id == conv.id)
        .order_by(Interaction.started_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .options(selectinload(Interaction.responses))
    )
    interactions = interactions_result.scalars().all()

    messages: list[ConversationMessage] = []
    for interaction in interactions:
        messages.append(ConversationMessage(role="user", content=interaction.prompt_text))

        if conv.feature == "AGREGADOR":
            for resp in sorted(interaction.responses, key=lambda r: r.created_at):
                if not resp.error_message:
                    citations, pubmed = read_response_metadata(resp.extra_metadata)
                    messages.append(ConversationMessage(
                        role="assistant",
                        content=resp.response_text,
                        mode=resp.model_used,
                        citations=citations,
                        pubmed_validation=pubmed,
                    ))
        else:
            # ORQUESTRADOR — single response, mode comes from interaction
            for resp in sorted(interaction.responses, key=lambda r: r.created_at):
                if not resp.error_message:
                    citations, pubmed = read_response_metadata(resp.extra_metadata)
                    messages.append(ConversationMessage(
                        role="assistant",
                        content=resp.response_text,
                        mode=interaction.mode,
                        citations=citations,
                        pubmed_validation=pubmed,
                    ))
                    break

    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        feature=conv.feature,
        messages=messages,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )
