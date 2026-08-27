from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import async_session_factory, get_db
from app.core.limiter import limiter
from app.models.models import User
from app.services.file_extractor_service import resolve_files_context
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
    mode: str | None = Field(
        default=None,
        description="Modo explícito (QUICK_SEARCH, CLINICAL_REASONING, PHARMA_CHECK, PHARMA_BULA, PHARMA_RECEITA, PHARMA_GENERICO, PRODUCTIVITY). Se informado, pula a triagem automática.",
    )
    folder_id: UUID | None = Field(
        default=None,
        description="Pasta onde a nova conversa será criada (opcional).",
    )
    file_id: UUID | None = Field(
        default=None,
        description=(
            "DEPRECADO — use `file_ids`. Mantido porque clientes antigos ainda "
            "enviam este campo; é tratado como uma lista de um elemento."
        ),
    )
    file_ids: list[UUID] = Field(
        default_factory=list,
        description=(
            "IDs de extrações enviadas via /uploads/extract. Até 5 por mensagem — "
            "cada imagem custa uma chamada de visão e pesa base64 no prompt."
        ),
    )

    def anexos(self) -> list[UUID]:
        """Anexos da mensagem, unificando o campo novo e o legado sem duplicar."""
        ids = list(self.file_ids)
        if self.file_id and self.file_id not in ids:
            ids.insert(0, self.file_id)
        return ids


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
    prompt, images, extractions = await resolve_files_context(body.prompt, body.anexos(), user.id, db)

    service = OrquestradorService(
        db=db,
        user_id=user.id,
        company_id=user.company_id,
        user_specialty=user.specialty,
        user_med_status=user.med_status,
    )
    return await service.query(
        prompt=prompt,
        conversation_id=body.conversation_id,
        force=body.force,
        clarification_answers=body.clarification_answers,
        mode=body.mode,
        folder_id=body.folder_id,
        image_content=images,
        # Ids, e não os objetos: o serviço de streaming abre a própria sessão,
        # e um objeto ORM preso a outra sessão não sobrevive à travessia.
        # Manter os dois caminhos iguais evita que só um deles quebre.
        attachment_ids=[e.id for e in extractions],
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
    prompt, images, extractions = await resolve_files_context(body.prompt, body.anexos(), user.id, db)

    service = OrquestradorStreamService(
        session_factory=async_session_factory,
        user_id=user.id,
        company_id=user.company_id,
        user_specialty=user.specialty,
        user_med_status=user.med_status,
    )
    return StreamingResponse(
        service.stream(
            prompt=prompt,
            conversation_id=body.conversation_id,
            force=body.force,
            clarification_answers=body.clarification_answers,
            effort=body.effort,
            mode=body.mode,
            folder_id=body.folder_id,
            image_content=images,
            attachment_ids=[e.id for e in extractions],
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",  # prevent GZipMiddleware from buffering SSE chunks
        },
    )