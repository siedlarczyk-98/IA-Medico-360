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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompts import (
    DISCLAIMER_RESPOSTA,
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
    PharmaAlert,
    PubmedValidation,
)
from app.services.ai_providers import get_provider_by_type, StreamToken
from app.services.medication_extractor import extract_from_interaction
from app.services.pricing import calculate_cost
from app.services.pubmed_service import validate_with_pubmed
from app.services.semantic_cache_service import get_cached_response, store_response
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.triage_service import triage

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


def _sse(event: str, data: dict) -> str:
    """Formata um evento SSE."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class OrquestradorStreamService:

    def __init__(self, db: AsyncSession, user_id: UUID, company_id: UUID | None = None):
        self.db = db
        self.user_id = user_id
        self.company_id = company_id

    async def stream(
        self,
        prompt: str,
        conversation_id: UUID | None = None,
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

        try:
            # 1. DLP
            dlp_result = sanitize_prompt(prompt)
            sanitized_prompt = dlp_result.sanitized_text

            # 2. Triage
            triage_result = await triage(sanitized_prompt)
            mode = triage_result["mode"]
            confidence = triage_result["confidence"]

            if confidence < 0.7:
                yield _sse("error", {
                    "status": "needs_refinement",
                    "message": "Preciso de um pouco mais de aprofundamento. Pode reformular com mais detalhes?",
                })
                return

            # PHARMA_CHECK não tem streaming — requer lógica separada
            if mode == "PHARMA_CHECK":
                yield _sse("error", {
                    "status": "unsupported_mode",
                    "message": "Modo Farmácia não suporta streaming. Use /query.",
                })
                return

            yield _sse("start", {"mode": mode, "triage_confidence": confidence})

            # 3. Cache lookup
            _cache_normalized: str = ""
            _cache_embedding: list = []
            if mode in {"QUICK_SEARCH", "CLINICAL_REASONING"}:
                cached, _cache_normalized, _cache_embedding = await get_cached_response(
                    self.db, mode, sanitized_prompt
                )
                if cached is not None:
                    yield _sse("cache_hit", {**cached, "cache_hit": True})
                    return

            # 4. Conversation + Interaction
            conv_id = await self._ensure_conversation(conversation_id, prompt)
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
            self.db.add(interaction)
            await self.db.flush()

            # 5. Streaming do modelo
            model_id = MODE_MODEL_MAP.get(mode)
            system_prompt = MODE_PROMPT_MAP.get(mode)
            temperature = MODE_TEMPERATURE_MAP.get(mode, 1.0)

            result = await self.db.execute(
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
                fallback_result = await self._fallback_complete(mode, sanitized_prompt, system_prompt)
                full_text = fallback_result.get("text", "")
                tokens_in = fallback_result.get("tokens_in")
                tokens_out = fallback_result.get("tokens_out")
                model_id = fallback_result.get("model_id", model_id)
                # streama o texto do fallback de uma vez
                yield _sse("token", {"text": full_text})

            # 6. Pós-processamento em background (não bloqueia o stream)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            cost = Decimal("0")
            if model_id and model_id != "pharmadb":
                cost = await calculate_cost(self.db, model_id, tokens_in, tokens_out)

            ir = InteractionResponse(
                interaction_id=interaction.id,
                model_used=model_id,
                response_text=full_text,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
                is_fallback=is_fallback,
            )
            self.db.add(ir)

            interaction.response_time_ms = elapsed_ms
            interaction.token_cost_usd = cost
            interaction.completed_at = datetime.now(timezone.utc)

            classification = await detect_specialty_and_topic(sanitized_prompt)
            interaction.specialty_detected = classification["specialty"]
            interaction.topic_detected = classification["topic"]

            medications = await extract_from_interaction(sanitized_prompt, [full_text])
            for med in medications:
                self.db.add(InteractionMedication(
                    interaction_id=interaction.id,
                    medication_raw=med["medication_raw"],
                    medication_normalized=med["medication_normalized"],
                    source=med["source"],
                ))

            pubmed = await validate_with_pubmed(
                agent_response=full_text,
                mode=mode,
                topic=classification.get("topic", ""),
            )
            interaction.confidence_score = pubmed.confidence_score

            for c in pubmed.cited_guidelines_verified:
                if c.pmid:
                    self.db.add(PubmedValidation(
                        interaction_id=interaction.id,
                        pmid=c.pmid,
                        article_title=c.title,
                        abstract_snippet=None,
                        relevance_score=1.0 if c.verified else 0.0,
                    ))
            for a in pubmed.newer_guidelines_found:
                self.db.add(PubmedValidation(
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
            self.db.add(audit)
            await self.db.flush()

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
                await store_response(self.db, mode, _cache_normalized, _cache_embedding, done_payload)

            # 7. Evento final com metadados
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
            yield _sse("error", {"message": "Erro interno. Tente novamente."})

    async def _fallback_complete(self, mode: str, prompt: str, system_prompt: str) -> dict:
        fallbacks = {
            "QUICK_SEARCH": ["gemini-2.5-flash"],
            "CLINICAL_REASONING": ["gpt-4o", "gemini-2.5-flash"],
            "PRODUCTIVITY": ["gemini-2.5-flash"],
        }
        for fallback_model in fallbacks.get(mode, []):
            result = await self.db.execute(
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

    async def _ensure_conversation(self, conversation_id: UUID | None, prompt: str) -> UUID:
        if conversation_id:
            result = await self.db.execute(
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
        self.db.add(conv)
        await self.db.flush()
        return conv.id
