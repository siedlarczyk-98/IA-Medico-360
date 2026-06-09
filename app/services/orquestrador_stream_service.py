"""
Médico 360 — Streaming do Orquestrador via SSE.

Pipeline:
  DLP → Triage → Cache lookup
    HIT  → yield evento JSON único com a resposta cacheada
    MISS → yield tokens do modelo em tempo real
           → ao final, roda PubMed + specialty + meds + audit em background
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.prompts import (
    DISCLAIMER_RESPOSTA,
    SYSTEM_PROMPT_CLARIFICATION,
    SYSTEM_PROMPT_CLINICAL_REASONING,
    SYSTEM_PROMPT_QUICK_SEARCH,
    SYSTEM_PROMPT_PRODUCTIVITY,
)
from app.middleware.dlp import sanitize_prompt
from app.models.models import (
    AuditLog,
    Conversation,
    Interaction,
    InteractionMedication,
    InteractionResponse,
    ModelPricing,
    PubmedValidation,
)
from app.services.ai_providers import OpenAIProvider, get_provider_by_type
from app.services.medication_extractor import extract_from_interaction
from app.services.pricing import calculate_cost
from app.services.usage_service import record_cost
from app.services.pubmed_service import validate_with_pubmed
from app.services.semantic_cache_service import get_cached_response, store_response
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.triage_service import triage, PHARMA_CHECK_MIN_CONFIDENCE

logger = logging.getLogger(__name__)

MODE_MODEL_MAP = {
    "QUICK_SEARCH": "sonar-pro",
    "CLINICAL_REASONING": "claude-sonnet-4-20250514",
    "PRODUCTIVITY": "gpt-5.4-nano",
}

MODE_PROMPT_MAP = {
    "QUICK_SEARCH": SYSTEM_PROMPT_QUICK_SEARCH,
    "CLINICAL_REASONING": SYSTEM_PROMPT_CLINICAL_REASONING,
    "PRODUCTIVITY": SYSTEM_PROMPT_PRODUCTIVITY,
}

MODE_TEMPERATURE_MAP = {
    "QUICK_SEARCH": 0.0,
    "CLINICAL_REASONING": 0.0,
    "PRODUCTIVITY": 0.7,
}


_clarification_provider = OpenAIProvider()
_CLARIFICATION_MODEL = "gpt-5.4-nano"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _check_clarification(prompt: str) -> dict:
    """
    Chama Haiku para verificar se o caso clínico tem contexto suficiente.
    Retorna {"sufficient": True} ou {"sufficient": False, "questions": [...]}.
    Falha silenciosa: se der erro, assume suficiente para não bloquear o fluxo.
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


class OrquestradorStreamService:

    def __init__(self, session_factory: async_sessionmaker, user_id: UUID, company_id: UUID | None = None):
        self.session_factory = session_factory
        self.user_id = user_id
        self.company_id = company_id

    async def stream(
        self,
        prompt: str,
        conversation_id: UUID | None = None,
        force: bool = False,
        clarification_answers: str | None = None,
        effort: str = "detalhado",
    ) -> AsyncIterator[str]:
        """
        Gerador SSE. Yields strings no formato 'event: ...\ndata: ...\n\n'.

        Eventos emitidos:
          - start        → modo e confiança da triagem
          - cache_hit    → resposta completa cacheada (encerra stream)
          - token        → fragmento de texto do modelo
          - done         → metadados finais (PubMed, custo, etc.)
          - error        → erro fatal
        """
        start_time = time.monotonic()

        async with self.session_factory() as db:
            try:
                # 1. Resolução de prompt: se há respostas de clarificação, monta contexto completo
                if clarification_answers and conversation_id:
                    prompt = await self._resolve_clarification_prompt(
                        db, conversation_id, clarification_answers
                    )

                # 2. DLP
                dlp_result = sanitize_prompt(prompt)
                sanitized_prompt = dlp_result.sanitized_text

                # 3. Triage
                triage_result = await triage(sanitized_prompt)
                mode = triage_result["mode"]
                confidence = triage_result["confidence"]

                if confidence < 0.7:
                    yield _sse("error", {
                        "status": "needs_refinement",
                        "message": "Preciso de um pouco mais de aprofundamento. Pode reformular com mais detalhes?",
                    })
                    return

                # PHARMA_CHECK requer alta confiança para acionar o serviço externo;
                # rebaixa para CLINICAL_REASONING se a pergunta for ambígua.
                if mode == "PHARMA_CHECK" and confidence < PHARMA_CHECK_MIN_CONFIDENCE:
                    mode = "CLINICAL_REASONING"

                if mode == "PHARMA_CHECK":
                    yield _sse("error", {
                        "status": "unsupported_mode",
                        "message": "Modo Farmácia não suporta streaming. Use /query.",
                    })
                    return

                # 4. Clarification check (apenas CLINICAL_REASONING, sem force, sem answers)
                if mode == "CLINICAL_REASONING" and not force and not clarification_answers:
                    clarification = await _check_clarification(sanitized_prompt)
                    if not clarification.get("sufficient", True):
                        questions = clarification.get("questions", [])
                        conv_id = await self._ensure_conversation(db, conversation_id, prompt)
                        pending = Interaction(
                            conversation_id=conv_id,
                            user_id=self.user_id,
                            company_id=self.company_id,
                            feature="ORQUESTRADOR",
                            mode=mode,
                            prompt_text=sanitized_prompt,
                            prompt_sanitized=dlp_result.was_sanitized,
                            triage_confidence=confidence,
                            triage_category=mode,
                            cache_hit=False,
                            status="pending_clarification",
                            clarification_questions=questions,
                            started_at=datetime.now(timezone.utc),
                        )
                        db.add(pending)
                        await db.commit()
                        yield _sse("clarification", {
                            "conversation_id": str(conv_id),
                            "questions": questions,
                        })
                        return

                yield _sse("start", {"mode": mode, "triage_confidence": confidence})

                # 6. Cache lookup
                _cache_normalized: str = ""
                _cache_embedding: list = []
                if mode in {"QUICK_SEARCH", "CLINICAL_REASONING"}:
                    cached, _cache_normalized, _cache_embedding = await get_cached_response(
                        db, mode, sanitized_prompt
                    )
                    if cached is not None:
                        yield _sse("cache_hit", {**cached, "cache_hit": True})
                        return

                # 4. Conversation + Interaction
                conv_id = await self._ensure_conversation(db, conversation_id, prompt)
                interaction = Interaction(
                    conversation_id=conv_id,
                    user_id=self.user_id,
                    company_id=self.company_id,
                    feature="ORQUESTRADOR",
                    mode=mode,
                    prompt_text=sanitized_prompt,
                    prompt_sanitized=dlp_result.was_sanitized,
                    triage_confidence=confidence,
                    triage_category=mode,
                    cache_hit=False,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(interaction)
                await db.flush()

                # 5. Streaming do modelo
                model_id = MODE_MODEL_MAP.get(mode)
                system_prompt = MODE_PROMPT_MAP.get(mode)
                if effort == "rápido" and system_prompt:
                    system_prompt = "Responda de forma direta e concisa, foco nos pontos essenciais.\n\n" + system_prompt
                temperature = MODE_TEMPERATURE_MAP.get(mode, 1.0)

                result = await db.execute(
                    select(ModelPricing).where(
                        ModelPricing.model_id == model_id,
                        ModelPricing.status == True,
                    )
                )
                model_info = result.scalar_one_or_none()

                if not model_info:
                    yield _sse("error", {"message": f"Modelo {model_id} não disponível."})
                    return

                provider = get_provider_by_type(model_info.provider_type)

                full_text = ""
                tokens_in: int | None = None
                tokens_out: int | None = None
                is_fallback = False

                try:
                    async for token in provider.stream(
                        model_id,
                        sanitized_prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                    ):
                        if token.delta:
                            full_text += token.delta
                            yield _sse("token", {"text": token.delta})
                        if token.done:
                            tokens_in = token.tokens_in
                            tokens_out = token.tokens_out

                except Exception as e:
                    logger.warning(f"Stream falhou em {model_id}: {e}. Tentando fallback completo...")
                    is_fallback = True
                    fallback_result = await self._fallback_complete(db, mode, sanitized_prompt, system_prompt)
                    full_text = fallback_result.get("text", "")
                    tokens_in = fallback_result.get("tokens_in")
                    tokens_out = fallback_result.get("tokens_out")
                    model_id = fallback_result.get("model_id", model_id)
                    yield _sse("token", {"text": full_text})

                # 6. Pós-processamento
                elapsed_ms = int((time.monotonic() - start_time) * 1000)

                cost = Decimal("0")
                if model_id and model_id != "pharmadb":
                    cost = await calculate_cost(db, model_id, tokens_in, tokens_out)

                ir = InteractionResponse(
                    interaction_id=interaction.id,
                    model_used=model_id,
                    response_text=full_text,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    is_fallback=is_fallback,
                )
                db.add(ir)

                interaction.response_time_ms = elapsed_ms
                interaction.token_cost_usd = cost
                interaction.completed_at = datetime.now(timezone.utc)

                # Pós-processamento independente roda em paralelo (specialty, meds, PubMed)
                # — cortando segundos da latência até o evento `done`. O PubMed usa o
                # próprio texto da resposta como fallback de tópico (topic=""), evitando
                # depender da detecção de especialidade para iniciar.
                classification, medications, pubmed = await asyncio.gather(
                    detect_specialty_and_topic(sanitized_prompt),
                    extract_from_interaction(sanitized_prompt, [full_text]),
                    validate_with_pubmed(agent_response=full_text, mode=mode, topic=""),
                )

                interaction.specialty_detected = classification["specialty"]
                interaction.topic_detected = classification["topic"]

                for med in medications:
                    db.add(InteractionMedication(
                        interaction_id=interaction.id,
                        medication_raw=med["medication_raw"],
                        medication_normalized=med["medication_normalized"],
                        source=med["source"],
                    ))

                interaction.confidence_score = pubmed.confidence_score

                for c in pubmed.cited_guidelines_verified:
                    if c.pmid:
                        db.add(PubmedValidation(
                            interaction_id=interaction.id,
                            pmid=c.pmid,
                            article_title=c.title,
                            abstract_snippet=None,
                            relevance_score=1.0 if c.verified else 0.0,
                        ))
                for a in pubmed.newer_guidelines_found:
                    db.add(PubmedValidation(
                        interaction_id=interaction.id,
                        pmid=a.pmid,
                        article_title=a.article_title,
                        abstract_snippet=a.abstract_snippet or None,
                        relevance_score=0.0,
                    ))

                audit = AuditLog(
                    user_id=self.user_id,
                    interaction_id=interaction.id,
                    action="orquestrador_stream",
                    entity_type="interaction",
                    entity_id=interaction.id,
                    metadata_={
                        "mode": mode,
                        "triage_confidence": confidence,
                        "model_used": model_id,
                        "is_fallback": is_fallback,
                        "prompt_length": len(prompt),
                        "total_cost_usd": str(cost),
                        "dlp_sanitized": dlp_result.was_sanitized,
                        "specialty_detected": classification["specialty"],
                        "topic_detected": classification["topic"],
                        "medications": [m["medication_normalized"] for m in medications],
                        "pubmed_confidence_score": pubmed.confidence_score,
                        "pubmed_low_evidence_alert": pubmed.low_evidence_alert,
                        "pubmed_outdated_alert": pubmed.outdated_alert,
                        "pubmed_fallback": pubmed.fallback,
                        "pubmed_cited_verified": sum(1 for c in pubmed.cited_guidelines_verified if c.verified),
                        "pubmed_newer_found": len(pubmed.newer_guidelines_found),
                    },
                )
                db.add(audit)

                # Store no cache
                if (
                    mode in {"QUICK_SEARCH", "CLINICAL_REASONING"}
                    and not is_fallback
                    and _cache_embedding
                    and _cache_normalized
                ):
                    done_payload = {
                        "status": "ok",
                        "cache_hit": False,
                        "interaction_id": str(interaction.id),
                        "conversation_id": str(conv_id),
                        "mode": mode,
                        "triage_confidence": confidence,
                        "model_used": model_id,
                        "is_fallback": is_fallback,
                        "response_text": full_text,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "cost_usd": float(cost),
                        "specialty_detected": classification["specialty"],
                        "topic_detected": classification["topic"],
                        "confidence_score": pubmed.confidence_score,
                        "low_evidence_alert": pubmed.low_evidence_alert,
                        "outdated_alert": pubmed.outdated_alert,
                        "cited_guidelines_verified": [
                            {"title": c.title, "pmid": c.pmid, "verified": c.verified}
                            for c in pubmed.cited_guidelines_verified
                        ],
                        "newer_guidelines_found": [
                            {"pmid": a.pmid, "title": a.article_title}
                            for a in pubmed.newer_guidelines_found
                        ],
                        "total_response_time_ms": elapsed_ms,
                        "disclaimer": DISCLAIMER_RESPOSTA,
                    }
                    await store_response(
                        db, mode, _cache_normalized, _cache_embedding, done_payload,
                        raw_prompt=sanitized_prompt,
                    )

                await record_cost(db, self.user_id, cost)

                # Commit explícito — sessão gerenciada aqui, não pelo get_db
                await db.commit()

                # 7. Evento final
                yield _sse("done", {
                    "interaction_id": str(interaction.id),
                    "conversation_id": str(conv_id),
                    "mode": mode,
                    "model_used": model_id,
                    "is_fallback": is_fallback,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": float(cost),
                    "specialty_detected": classification["specialty"],
                    "topic_detected": classification["topic"],
                    "confidence_score": pubmed.confidence_score,
                    "low_evidence_alert": pubmed.low_evidence_alert,
                    "outdated_alert": pubmed.outdated_alert,
                    "cited_guidelines_verified": [
                        {"title": c.title, "pmid": c.pmid, "verified": c.verified}
                        for c in pubmed.cited_guidelines_verified
                    ],
                    "newer_guidelines_found": [
                        {"pmid": a.pmid, "title": a.article_title}
                        for a in pubmed.newer_guidelines_found
                    ],
                    "total_response_time_ms": elapsed_ms,
                    "disclaimer": DISCLAIMER_RESPOSTA,
                })

            except Exception as e:
                logger.error(f"ERRO NO STREAM: {e}")
                await db.rollback()
                yield _sse("error", {"message": "Erro interno. Tente novamente."})

    async def _fallback_complete(self, db, mode: str, prompt: str, system_prompt: str) -> dict:
        fallbacks = {
            "QUICK_SEARCH": ["gemini-2.5-flash"],
            "CLINICAL_REASONING": ["gpt-4o", "gemini-2.5-flash"],
            "PRODUCTIVITY": ["gemini-2.5-flash"],
        }
        for fallback_model in fallbacks.get(mode, []):
            result = await db.execute(
                select(ModelPricing).where(
                    ModelPricing.model_id == fallback_model,
                    ModelPricing.status == True,
                )
            )
            model_info = result.scalar_one_or_none()
            if not model_info:
                continue
            try:
                provider = get_provider_by_type(model_info.provider_type)
                response = await provider.complete(fallback_model, prompt, system_prompt=system_prompt)
                return {
                    "text": response.text,
                    "model_id": fallback_model,
                    "tokens_in": response.tokens_in,
                    "tokens_out": response.tokens_out,
                }
            except Exception:
                continue
        return {
            "text": "Desculpe, não foi possível processar sua consulta no momento.",
            "model_id": MODE_MODEL_MAP.get(mode, "unknown"),
            "tokens_in": None,
            "tokens_out": None,
        }

    async def _resolve_clarification_prompt(
        self, db, conversation_id: UUID, clarification_answers: str
    ) -> str:
        """
        Busca a Interaction pending_clarification da conversa e monta o prompt
        consolidado: pergunta original + perguntas + respostas do médico.
        Se não encontrar, retorna apenas as respostas (fallback sem perda).
        """
        result = await db.execute(
            select(Interaction).where(
                Interaction.conversation_id == conversation_id,
                Interaction.user_id == self.user_id,
                Interaction.status == "pending_clarification",
            ).order_by(Interaction.started_at.desc()).limit(1)
        )
        pending = result.scalar_one_or_none()

        if not pending:
            return clarification_answers

        questions = pending.clarification_questions or []
        questions_text = "\n".join(f"- {q}" for q in questions)

        consolidated = (
            f"{pending.prompt_text}\n\n"
            f"Informações complementares solicitadas:\n{questions_text}\n\n"
            f"Respostas do médico:\n{clarification_answers}"
        )

        # Marca a interaction pendente como substituída
        pending.status = "resolved"
        await db.flush()

        return consolidated

    async def _ensure_conversation(self, db, conversation_id: UUID | None, prompt: str) -> UUID:
        if conversation_id:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == self.user_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                return conv.id

        title = prompt[:100] + ("..." if len(prompt) > 100 else "")
        conv = Conversation(
            user_id=self.user_id,
            title=title,
            feature="ORQUESTRADOR",
        )
        db.add(conv)
        await db.flush()
        return conv.id
