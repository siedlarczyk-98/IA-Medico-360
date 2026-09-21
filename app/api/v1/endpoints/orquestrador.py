import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import async_session_factory, get_db
from app.core.limiter import limiter
from app.core.sse import com_heartbeat
from app.models.models import User
from app.services.file_extractor_service import resolve_files_context
from app.services.orquestrador_service import OrquestradorService
from app.services.orquestrador_stream_service import OrquestradorStreamService
from app.services.usage_service import check_limit

logger = logging.getLogger(__name__)

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
        description="Modo explícito (QUICK_SEARCH, CLINICAL_REASONING, PHARMA_CHECK, PHARMA_BULA, PHARMA_RECEITA, PHARMA_GENERICO, PRODUCTIVITY, EXAM_REVIEW, DATA_OCEAN). Se informado, pula a triagem automática. DATA_OCEAN só chega por aqui: a triagem nunca o escolhe.",
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


@router.post("/query", deprecated=True)
@limiter.limit("30/minute")
async def orquestrador_query(
    request: Request,
    response: Response,
    body: OrquestradorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    OBSOLETA desde 2026-09-21 — use `/stream`. Em observação antes de sair.

    Era o caminho dos modos de farmácia, que o stream recusava. O stream passou a
    atendê-los, e o único chamador conhecido (o ramo `unsupported_mode` do chat)
    nunca mais é acionado. Manter os dois caminhos do orquestrador em paralelo já
    causou três bugs de divergência num dia.

    Não foi apagada de uma vez porque NÃO SE SABE se existe chamador de fora do
    monorepo. Cada chamada agora deixa rastro (`orquestrador_query_obsoleto` no
    log, com origem e user-agent): uma ou duas semanas sem nenhuma ocorrência é o
    sinal para remover a rota, o `OrquestradorService.query` e os testes de
    paridade. Os handlers de farmácia do serviço FICAM — o stream os usa.

    Orquestrador Multi-Agente.
    Faz triagem automática da pergunta e roteia pro agente especializado:
    - QUICK_SEARCH → Perplexity (respostas rápidas com fontes)
    - CLINICAL_REASONING → Claude Sonnet (raciocínio clínico avançado)
    - PHARMA_CHECK → PharmaDB (interações medicamentosas entre 2+ fármacos)
    - PHARMA_BULA → PharmaDB (bula completa de um medicamento)
    - PHARMA_RECEITA → PharmaDB (receituário e dispensação — Portaria 344)
    - PHARMA_GENERICO → PharmaDB (genéricos e similares intercambiáveis)
    - PRODUCTIVITY → GPT-5.4 Nano (tarefas não clínicas)
    - DATA_OCEAN → Sabiá 4 Thinking (bases públicas brasileiras: DATASUS, CNES,
      ANVISA, InfoDengue, IBGE). Só por escolha explícita do médico. Não
      streama de verdade e pode levar dezenas de segundos: o fluxo agêntico
      roda inteiro na Maritaca antes de devolver a resposta.
    """
    logger.warning(
        "orquestrador_query_obsoleto: rota /orquestrador/query ainda em uso",
        extra={
            "user_id": str(user.id),
            "origem": request.headers.get("origin"),
            "referer": request.headers.get("referer"),
            "user_agent": request.headers.get("user-agent"),
            "modo": body.mode,
        },
    )
    # Cabeçalhos padrão (RFC 9745 / 8594): um cliente bem-comportado os registra.
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</api/v1/orquestrador/stream>; rel="successor-version"'

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
    - text_done  → texto completo; o cliente já pode liberar a digitação
    - done       → metadados finais (PubMed, custo, specialty, etc.)
    - error      → erro fatal

    Os modos de farmácia também são atendidos aqui: a base responde de uma vez,
    então o texto chega num único evento `token`.
    """
    await check_limit(db, user)
    prompt, images, extractions = await resolve_files_context(body.prompt, body.anexos(), user.id, db)
    attachment_ids = [e.id for e in extractions]

    # DEVOLVE A CONEXÃO AGORA. O FastAPI só encerra a dependência `get_db` depois
    # de enviar o corpo — e o corpo aqui é um stream de 13 a 57 segundos. Sem este
    # commit a sessão da requisição ficava ociosa DENTRO de uma transação por
    # toda a resposta, segurando uma conexão do pool sem fazer nada. Somada à do
    # serviço de stream eram DUAS por resposta: cerca de 20 respostas simultâneas
    # esgotavam o pool (30+10), e a partir daí toda requisição autenticada
    # esperava 30 s e falhava. Depois do commit a sessão continua válida, só não
    # segura conexão; o `get_db` a fecha no fim como sempre.
    await db.commit()

    service = OrquestradorStreamService(
        session_factory=async_session_factory,
        user_id=user.id,
        company_id=user.company_id,
        user_specialty=user.specialty,
        user_med_status=user.med_status,
    )
    return StreamingResponse(
        # `com_heartbeat`: `: ping` a cada 15 s de silêncio, para proxy e
        # balanceador não cortarem o stream enquanto o modelo pensa.
        com_heartbeat(service.stream(
            prompt=prompt,
            conversation_id=body.conversation_id,
            force=body.force,
            clarification_answers=body.clarification_answers,
            effort=body.effort,
            mode=body.mode,
            folder_id=body.folder_id,
            image_content=images,
            attachment_ids=attachment_ids,
        )),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",  # prevent GZipMiddleware from buffering SSE chunks
        },
    )