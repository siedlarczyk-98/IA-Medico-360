"""
Médico 360 — Endpoints do Agregador de IA.
POST /query       → Consulta (non-streaming)
POST /stream      → Consulta com SSE streaming
GET  /models      → Lista modelos disponíveis
GET  /history     → Histórico de consultas
"""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.prompts import DISCLAIMER_RESPOSTA
from app.models.models import User
from app.schemas.agregador import (
    AgregadorRequest,
    AgregadorResponse,
    AIModelDisplay,
    AIModelEnum,
    HistorySearchParams,
    InteractionHistoryItem,
    ModelResponse,
)
from app.services.agregador_service import AgregadorService
from app.services.ai_providers import get_provider

router = APIRouter(prefix="/agregador", tags=["Agregador de IA"])


# ── Modelos Disponíveis ──────────────────────────────────────

MODELS_CATALOG = [
    AIModelDisplay(
        model_id=AIModelEnum.CLAUDE_SONNET,
        provider="Anthropic",
        display_name="Claude Sonnet 4",
        use_case="Raciocínio clínico avançado",
        cost_tier="médio",
    ),
    AIModelDisplay(
        model_id=AIModelEnum.GPT_4O,
        provider="OpenAI",
        display_name="GPT-4o",
        use_case="Consultas gerais",
        cost_tier="médio",
    ),
    AIModelDisplay(
        model_id=AIModelEnum.GEMINI_FLASH,
        provider="Google",
        display_name="Gemini 2.5 Flash",
        use_case="Respostas rápidas",
        cost_tier="baixo",
    ),
    AIModelDisplay(
        model_id=AIModelEnum.PERPLEXITY_SONAR,
        provider="Perplexity",
        display_name="Perplexity Sonar Pro",
        use_case="Busca online com fontes",
        cost_tier="médio",
    ),
]


@router.get("/models", response_model=list[AIModelDisplay])
async def list_models():
    """Retorna os modelos de IA disponíveis no Agregador."""
    return MODELS_CATALOG


# ── Consulta (Non-Streaming) ────────────────────────────────

@router.post("/query", response_model=AgregadorResponse)
async def agregador_query(
    request: AgregadorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Envia consulta ao Agregador de IA.
    Chama os modelos selecionados em paralelo e retorna todas as respostas.
    """
    service = AgregadorService(
        db=db,
        user_id=user.id,
        company_id=user.company_id,
    )
    return await service.query(request)


# ── Consulta com Streaming (SSE) ────────────────────────────

@router.post("/stream")
async def agregador_stream(
    request: AgregadorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    RN-UX-003: Respostas via streaming (token a token) para percepção de velocidade.
    Retorna Server-Sent Events com chunks de cada modelo.
    """

    async def event_generator():
        tasks = {}
        for model in request.models:
            provider = get_provider(model.value)
            tasks[model.value] = provider.stream(request.prompt)

        # Stream de cada modelo como eventos SSE separados
        async def stream_model(model_id: str, provider_stream):
            start = time.monotonic()
            full_text = ""
            try:
                async for token in provider_stream:
                    if token.delta:
                        full_text += token.delta
                        yield {
                            "event": "delta",
                            "data": json.dumps({
                                "model_id": model_id,
                                "delta": token.delta,
                            }),
                        }
                    if token.done:
                        elapsed = int((time.monotonic() - start) * 1000)
                        yield {
                            "event": "complete",
                            "data": json.dumps({
                                "model_id": model_id,
                                "response_time_ms": elapsed,
                                "tokens_in": token.tokens_in,
                                "tokens_out": token.tokens_out,
                            }),
                        }
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "model_id": model_id,
                        "error": str(e),
                    }),
                }

        # Intercalar streams de todos os modelos
        queues: dict[str, asyncio.Queue] = {}
        active_tasks = set()

        for model_id, provider_stream in tasks.items():
            q: asyncio.Queue = asyncio.Queue()
            queues[model_id] = q

            async def _run(mid=model_id, ps=provider_stream, queue=q):
                async for event in stream_model(mid, ps):
                    await queue.put(event)
                await queue.put(None)  # sentinel

            task = asyncio.create_task(_run())
            active_tasks.add(task)

        # Yield events as they arrive
        done_count = 0
        total = len(queues)
        while done_count < total:
            for model_id, q in queues.items():
                try:
                    event = q.get_nowait()
                    if event is None:
                        done_count += 1
                    else:
                        yield event
                except asyncio.QueueEmpty:
                    pass
            await asyncio.sleep(0.01)

        # Final disclaimer
        yield {
            "event": "disclaimer",
            "data": json.dumps({"text": DISCLAIMER_RESPOSTA}),
        }
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


# ── Histórico ────────────────────────────────────────────────

@router.get("/history", response_model=list[InteractionHistoryItem])
async def get_history(
    params: HistorySearchParams = Depends(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    RN-AGR-004: histórico pesquisável por data, modelo e palavras-chave.
    """
    service = AgregadorService(db=db, user_id=user.id)
    interactions = await service.get_history(
        query=params.query,
        model_filter=params.model_filter.value if params.model_filter else None,
        date_from=params.date_from,
        date_to=params.date_to,
        page=params.page,
        page_size=params.page_size,
    )

    items = []
    for i in interactions:
        models_used = [r.model_used for r in (i.responses or [])]
        items.append(
            InteractionHistoryItem(
                interaction_id=i.id,
                prompt_text=i.prompt_text,
                feature=i.feature.value,
                mode=i.mode.value if i.mode else None,
                models_used=models_used,
                response_time_ms=i.response_time_ms,
                cache_hit=i.cache_hit,
                created_at=i.createdat,
            )
        )
    return items
