from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_current_user
from app.core.database import get_db, async_session_factory
from app.models.models import User
from app.schemas.agregador import ConversationMessage
from app.services.orquestrador_service import OrquestradorService
from app.services.orquestrador_stream_service import OrquestradorStreamService
from app.services.usage_service import check_limit
from app.core.limiter import limiter

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
    mode: str | None = Field(
        default=None,
        description="Modo explícito (QUICK_SEARCH, CLINICAL_REASONING, PHARMA_CHECK, PHARMA_BULA, PHARMA_RECEITA, PHARMA_GENERICO, PRODUCTIVITY). Se informado, pula a triagem automática.",
    )
    history: list[ConversationMessage] = Field(
        default_factory=list,
        description="Histórico de mensagens anteriores da conversa (até 10 turnos usados).",
    )
    folder_id: UUID | None = Field(
        default=None,
        description="Pasta onde a nova conversa será criada (opcional).",
    )


@router.post("/query")
@limiter.limit("30/minute")
async def orquestrador_query(
    request: Request,
    body: OrquestradorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Orquestrador Multi-Agente.
    Faz triagem automática da pergunta e roteia pro agente especializado:
    - QUICK_SEARCH → Perplexity (respostas rápidas com fontes)
    - CLINICAL_REASONING → Claude Sonnet (raciocínio clínico avançado)
    - PHARMA_CHECK → PharmaDB (interações medicamentosas entre 2+ fármacos)
    - PHARMA_BULA → PharmaDB (bula completa de um medicamento)
    - PHARMA_RECEITA → PharmaDB (receituário e dispensação — Portaria 344)
    - PHARMA_GENERICO → PharmaDB (genéricos e similares intercambiáveis)
    - PRODUCTIVITY → GPT-5.4 Nano (tarefas não clínicas)
    """
    await check_limit(db, user)
    await db.commit()

    service = OrquestradorService(
        db=db,
        user_id=user.id,
        company_id=user.company_id,
        user_specialty=user.specialty,
        user_med_status=user.med_status,
    )
    return await service.query(
        prompt=body.prompt,
        conversation_id=body.conversation_id,
        force=body.force,
        clarification_answers=body.clarification_answers,
        mode=body.mode,
        history=body.history or [],
        folder_id=body.folder_id,
    )


@router.post("/stream")
@limiter.limit("30/minute")
async def orquestrador_stream(
    request: Request,
    body: OrquestradorRequest,
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
        user_specialty=user.specialty,
        user_med_status=user.med_status,
    )
    return StreamingResponse(
        service.stream(
            prompt=body.prompt,
            conversation_id=body.conversation_id,
            force=body.force,
            clarification_answers=body.clarification_answers,
            effort=body.effort,
            mode=body.mode,
            history=body.history or [],
            folder_id=body.folder_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",  # prevent GZipMiddleware from buffering SSE chunks
        },
    )