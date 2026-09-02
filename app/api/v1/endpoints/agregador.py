"""
Médico 360 — Endpoints do Agregador de IA.
POST /query       → Consulta (non-streaming)
POST /stream      → Consulta com SSE streaming
GET  /models      → Lista modelos disponíveis (do banco)
GET  /history     → Histórico de consultas
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.prompts import DISCLAIMER_RESPOSTA, build_agregador_prompt
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import ModelPricing, User
from app.schemas.agregador import (
    AgregadorRequest,
    AgregadorResponse,
    AIModelDisplay,
    HistorySearchParams,
    InteractionHistoryItem,
)
from app.services.agregador_service import AgregadorService
from app.services.file_extractor_service import resolve_file_context
from app.services.integracoes.ai_providers import get_provider_by_type
from app.services.usage_service import check_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agregador", tags=["Agregador de IA"])


# ── Modelos Disponíveis (do banco) ───────────────────────────

@router.get("/models", response_model=list[AIModelDisplay])
async def list_models(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna todos os modelos ativos do banco, indicando disponibilidade."""
    settings = get_settings()

    placeholders = {"", "xxx", "sk-ant-xxx", "pplx-xxx", "sk-xxx"}

    key_map = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "google": settings.google_ai_api_key,
        "perplexity": settings.perplexity_api_key,
    }

    result = await db.execute(
        select(ModelPricing).where(ModelPricing.status.is_(True)).order_by(ModelPricing.provider)
    )
    models = result.scalars().all()

    return [
        AIModelDisplay(
            model_id=m.model_id,
            provider=m.provider,
            display_name=m.display_name,
            cost_tier=_get_cost_tier(m.input_per_million),
            available=key_map.get(m.provider_type, "") not in placeholders,
            supports_vision=m.provider_type != "perplexity",
        )
        for m in models
    ]


def _get_cost_tier(input_per_million) -> str:
    """Classifica o custo em baixo/médio/alto baseado no preço de input."""
    price = float(input_per_million)
    if price < 0.50:
        return "baixo"
    elif price < 5.00:
        return "médio"
    else:
        return "alto"


# ── Consulta (Non-Streaming) ────────────────────────────────

@router.post("/query", response_model=AgregadorResponse)
@limiter.limit("30/minute")
async def agregador_query(
    request: Request,
    body: AgregadorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Envia consulta ao Agregador de IA.
    Chama os modelos selecionados em paralelo e retorna todas as respostas.
    """
    await check_limit(db, user)

    # Caminho non-streaming não suporta visão — imagens entram como texto (descrição).
    body.prompt, _ = await resolve_file_context(
        body.prompt, body.file_id, user.id, db, support_vision=False
    )

    service = AgregadorService(
        db=db,
        user_id=user.id,
        company_id=user.company_id,
    )
    system_prompt = build_agregador_prompt(user.specialty, user.med_status)
    return await service.query(body, system_prompt=system_prompt)


# ── Consulta com Streaming (SSE) ────────────────────────────

@router.post("/stream")
@limiter.limit("30/minute")
async def agregador_stream(
    request: Request,
    body: AgregadorRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    RN-UX-003: Respostas via streaming (token a token).
    Retorna Server-Sent Events com chunks de cada modelo.
    """

    await check_limit(db, user)

    # Imagens: envia os pixels reais como vision block; descrição (já sanitizada na
    # extração) vai como fallback para providers sem visão (Perplexity).
    body.prompt, image_content = await resolve_file_context(
        body.prompt, body.file_id, user.id, db
    )

    service = AgregadorService(db=db, user_id=user.id, company_id=user.company_id)

    # DLP antes de qualquer coisa
    dlp_result = await sanitize_prompt_async(body.prompt)
    sanitized_prompt = dlp_result.sanitized_text

    # Criar/recuperar conversa (já usa prompt sanitizado no título)
    conversation_id = await service._ensure_conversation(body.conversation_id, sanitized_prompt, folder_id=body.folder_id)
    await db.commit()

    # Montar prompt enriquecido com histórico recebido do frontend
    if body.history:
        parts = ["[Conversa anterior]"]
        for msg in body.history[-10:]:
            role_label = "Médico" if msg.role == "user" else "Assistente"
            parts.append(f"{role_label}: {msg.content[:800]}")
        parts.append("[Pergunta atual]")
        enriched_prompt = "\n".join(parts) + f"\nMédico: {sanitized_prompt}"
    else:
        enriched_prompt = sanitized_prompt

    # Buscar modelos no banco
    result = await db.execute(
        select(ModelPricing).where(
            ModelPricing.model_id.in_(body.models),
            ModelPricing.status.is_(True),
        )
    )
    models_info = {m.model_id: m for m in result.scalars().all()}

    base_system_prompt = build_agregador_prompt(user.specialty, user.med_status)
    if body.effort == "rápido":
        effort_system = "Responda de forma direta e concisa, foco nos pontos essenciais.\n\n" + base_system_prompt
        effort_max_tokens = 700
    else:
        effort_system = base_system_prompt
        effort_max_tokens = 4096

    stream_start = time.monotonic()

    async def event_generator():
        # Acumula texto + tokens por modelo para salvar após stream
        collected: dict[str, dict] = {
            mid: {"text": "", "tokens_in": None, "tokens_out": None, "error": None, "search_cost_usd": 0.0}
            for mid in models_info
        }

        # Fila única compartilhada — cada task escreve nela; consumer faz await get()
        # eliminando o busy-loop com get_nowait() + sleep(0.01).
        shared_q: asyncio.Queue = asyncio.Queue()
        total = len(models_info)
        # `asyncio` só guarda referência fraca para a task. Sem manter a
        # referência aqui, o coletor pode recolher uma consulta em voo e o
        # consumidor abaixo ficaria esperando uma sentinela que nunca chega.
        tarefas: set[asyncio.Task] = set()

        for model_id, model_info in models_info.items():
            provider = get_provider_by_type(model_info.provider_type)
            provider_stream = provider.stream(model_id, enriched_prompt, system_prompt=effort_system, web_search=body.web_search.get(model_id, False), image_content=image_content, max_tokens=effort_max_tokens)
            model_start = time.monotonic()

            async def _run(mid=model_id, ps=provider_stream, mstart=model_start):
                try:
                    async for token in ps:
                        if token.delta:
                            collected[mid]["text"] += token.delta
                            await shared_q.put({
                                "event": "delta",
                                "data": json.dumps({"model_id": mid, "delta": token.delta}),
                            })
                        if token.done:
                            collected[mid]["tokens_in"] = token.tokens_in
                            collected[mid]["tokens_out"] = token.tokens_out
                            collected[mid]["citations"] = token.citations or []
                            collected[mid]["search_cost_usd"] = token.search_cost_usd
                            elapsed = int((time.monotonic() - mstart) * 1000)
                            await shared_q.put({
                                "event": "complete",
                                "data": json.dumps({
                                    "model_id": mid,
                                    "response_time_ms": elapsed,
                                    "tokens_in": token.tokens_in,
                                    "tokens_out": token.tokens_out,
                                    "citations": token.citations,
                                }),
                            })
                except Exception as e:
                    # Loga o erro real internamente, mas não expõe detalhes ao cliente.
                    logger.warning("Falha no modelo %s: %s", mid, e)
                    collected[mid]["error"] = str(e)
                    await shared_q.put({
                        "event": "error",
                        "data": json.dumps({
                            "model_id": mid,
                            "error": f"Falha ao consultar o modelo {mid}. Tente novamente.",
                        }),
                    })
                finally:
                    await shared_q.put(None)  # sentinela de conclusão deste modelo

            tarefa = asyncio.create_task(_run())
            tarefas.add(tarefa)
            tarefa.add_done_callback(tarefas.discard)

        done_count = 0
        while done_count < total:
            event = await shared_q.get()
            if event is None:
                done_count += 1
            else:
                yield event

        # Salvar interação no banco após stream completo
        elapsed_ms = int((time.monotonic() - stream_start) * 1000)
        pubmed_results = {}
        try:
            _interaction_id, pubmed_results = await service.save_stream_interaction(
                conversation_id=conversation_id,
                sanitized_prompt=sanitized_prompt,
                prompt_sanitized=dlp_result.was_sanitized,
                collected=collected,
                elapsed_ms=elapsed_ms,
            )
        except Exception as e:
            logger.error(f"Erro ao salvar interação stream: {e}")

        # Emite resultados PubMed por modelo (só quando há citações verificadas)
        for mid, pub in pubmed_results.items():
            yield {
                "event": "pubmed",
                "data": json.dumps({
                    "model_id": mid,
                    "cited_verified": [c.model_dump() for c in pub.cited_guidelines_verified],
                    "newer_guidelines": [a.model_dump() for a in pub.newer_guidelines_found],
                }),
            }

        yield {"event": "disclaimer", "data": json.dumps({"text": DISCLAIMER_RESPOSTA})}
        yield {"event": "done", "data": json.dumps({"conversation_id": str(conversation_id)})}

    return EventSourceResponse(
        event_generator(),
        headers={"Content-Encoding": "identity"},  # prevent GZipMiddleware from buffering SSE chunks
    )


# ── Histórico ────────────────────────────────────────────────

@router.get("/history", response_model=list[InteractionHistoryItem])
async def get_history(
    params: HistorySearchParams = Depends(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RN-AGR-004: histórico pesquisável por data, modelo e palavras-chave."""
    service = AgregadorService(db=db, user_id=user.id)
    interactions = await service.get_history(
        query=params.query,
        model_filter=params.model_filter,
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
                feature=i.feature,
                mode=i.mode,
                models_used=models_used,
                response_time_ms=i.response_time_ms,
                cache_hit=i.cache_hit,
                created_at=i.created_at,
            )
        )
    return items