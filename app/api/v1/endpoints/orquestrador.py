from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_current_user
from app.core.database import get_db, async_session_factory
from app.models.models import User
from app.services.orquestrador_service import OrquestradorService
from app.services.orquestrador_stream_service import OrquestradorStreamService
from app.services.usage_service import check_limit

router = APIRouter(prefix="/orquestrador", tags=["Orquestrador Multi-Agente"])


class OrquestradorRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Pergunta do médico",
    )
    conversation_id: UUID | None = Field(
        default=None,
        description="ID da conversa existente (ou None para criar nova)",
    )
    force: bool = Field(
        default=False,
        description="Se true, pula a etapa de clarificação e executa o pipeline completo diretamente.",
    )
    clarification_answers: str | None = Field(
        default=None,
        description="Respostas do médico às perguntas de clarificação. Quando presente, o backend busca o prompt original e monta o contexto completo.",
    )
    effort: str = Field(
        default="detalhado",
        description="Nível de esforço da resposta: 'rápido' (conciso) ou 'detalhado' (padrão).",
    )


@router.post("/query")
async def orquestrador_query(
    request: OrquestradorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Orquestrador Multi-Agente.
    Faz triagem automática da pergunta e roteia pro agente especializado:
    - QUICK_SEARCH → Perplexity (respostas rápidas com fontes)
    - CLINICAL_REASONING → Claude Sonnet (raciocínio clínico avançado)
    - PHARMA_CHECK → PharmaDB (interações medicamentosas)
    - PRODUCTIVITY → GPT-5.4 Nano (tarefas não clínicas)
    """
    await check_limit(db, user)
    await db.commit()

    service = OrquestradorService(
        db=db,
        user_id=user.id,
        company_id=user.company_id,
    )
    return await service.query(
        prompt=request.prompt,
        conversation_id=request.conversation_id,
        force=request.force,
        clarification_answers=request.clarification_answers,
    )


@router.post("/stream")
async def orquestrador_stream(
    request: OrquestradorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Orquestrador Multi-Agente com streaming SSE (Server-Sent Events).
    Retorna tokens em tempo real conforme o modelo gera a resposta.

    Eventos SSE:
    - start      → modo e confiança da triagem
    - cache_hit  → resposta completa cacheada (encerra stream)
    - token      → fragmento de texto do modelo
    - done       → metadados finais (PubMed, custo, specialty, etc.)
    - error      → erro fatal

    Não suporta PHARMA_CHECK — use /query para interações medicamentosas.
    """
    await check_limit(db, user)
    await db.commit()

    service = OrquestradorStreamService(
        session_factory=async_session_factory,
        user_id=user.id,
        company_id=user.company_id,
    )
    return StreamingResponse(
        service.stream(
            prompt=request.prompt,
            conversation_id=request.conversation_id,
            force=request.force,
            clarification_answers=request.clarification_answers,
            effort=request.effort,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )