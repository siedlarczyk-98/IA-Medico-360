"""
Médico 360 — Serviço do Orquestrador Multi-Agente.
Pipeline: Triagem → Roteamento → Agente Especializado → Resposta.
"""

import logging
import time
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompts import (
    DISCLAIMER_RESPOSTA,
    SYSTEM_PROMPT_CLINICAL_REASONING,
    SYSTEM_PROMPT_PRODUCTIVITY,
    SYSTEM_PROMPT_QUICK_SEARCH,
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
from app.services.ai_providers import get_provider_by_type
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
    "PHARMA_CHECK": None,
    "PRODUCTIVITY": "gpt-5.4-nano",
}

# temperature=0 para modos clínicos garante respostas consistentes e reproduzíveis
MODE_TEMPERATURE_MAP = {
    "QUICK_SEARCH": 0.0,
    "CLINICAL_REASONING": 0.0,
    "PRODUCTIVITY": 0.7,
}

MODE_PROMPT_MAP = {
    "QUICK_SEARCH": SYSTEM_PROMPT_QUICK_SEARCH,
    "CLINICAL_REASONING": SYSTEM_PROMPT_CLINICAL_REASONING,
    "PRODUCTIVITY": SYSTEM_PROMPT_PRODUCTIVITY,
}


class OrquestradorService:
    """Serviço principal do Orquestrador Multi-Agente."""

    def __init__(self, db: AsyncSession, user_id: UUID, company_id: UUID | None = None):
        self.db = db
        self.user_id = user_id
        self.company_id = company_id

    async def query(self, prompt: str, conversation_id: UUID | None = None) -> dict:
        try:
            start_time = time.monotonic()

            # 1. DLP
            dlp_result = sanitize_prompt(prompt)
            sanitized_prompt = dlp_result.sanitized_text

            # 2. Triagem (The Gatekeeper)
            triage_result = await triage(sanitized_prompt)
            mode = triage_result["mode"]
            confidence = triage_result["confidence"]

            if confidence < 0.7:
                return {
                    "status": "needs_refinement",
                    "mode": mode,
                    "confidence": confidence,
                    "message": "Preciso de um pouco mais de aprofundamento para te indicar o agente correto. Pode reformular com mais detalhes?",
                    "disclaimer": DISCLAIMER_RESPOSTA,
                }

            # 3. Cache semântico (apenas modos clínicos)
            _cache_normalized: str = ""
            _cache_embedding: list = []
            if mode in {"QUICK_SEARCH", "CLINICAL_REASONING"}:
                cached, _cache_normalized, _cache_embedding = await get_cached_response(
                    self.db, mode, sanitized_prompt
                )
                if cached is not None:
                    return {**cached, "cache_hit": True}

            # 4. Conversation
            conv_id = await self._ensure_conversation(conversation_id, prompt)

            # 5. Interaction
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

            # 5. Roteamento pro agente
            if mode == "PHARMA_CHECK":
                agent_response = await self._handle_pharma_check(sanitized_prompt, interaction.id)
            else:
                agent_response = await self._handle_ai_agent(mode, sanitized_prompt)

            # 6. Salvar resposta
            cost = Decimal("0")
            if agent_response.get("model_id") and agent_response.get("model_id") != "pharmadb":
                cost = await calculate_cost(
                    self.db,
                    agent_response["model_id"],
                    agent_response.get("tokens_in"),
                    agent_response.get("tokens_out"),
                )

            ir = InteractionResponse(
                interaction_id=interaction.id,
                model_used=agent_response.get("model_id", "pharmadb"),
                response_text=agent_response.get("text", ""),
                tokens_in=agent_response.get("tokens_in"),
                tokens_out=agent_response.get("tokens_out"),
                cost_usd=cost,
                is_fallback=agent_response.get("is_fallback", False),
                error_message=agent_response.get("error"),
            )
            self.db.add(ir)

            # 7. Finalizar interaction
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            interaction.response_time_ms = elapsed_ms
            interaction.token_cost_usd = cost
            interaction.completed_at = datetime.now(timezone.utc)

            # 8. Especialidade + tema
            classification = await detect_specialty_and_topic(sanitized_prompt)
            interaction.specialty_detected = classification["specialty"]
            interaction.topic_detected = classification["topic"]

            # 9. Medicamentos
            response_texts = [agent_response.get("text", "")]
            medications = await extract_from_interaction(sanitized_prompt, response_texts)
            for med in medications:
                self.db.add(InteractionMedication(
                    interaction_id=interaction.id,
                    medication_raw=med["medication_raw"],
                    medication_normalized=med["medication_normalized"],
                    source=med["source"],
                ))

            # 10. Validação PubMed (apenas modos clínicos; timeout 15s com fallback)
            pubmed = await validate_with_pubmed(
                agent_response=agent_response.get("text", ""),
                mode=mode,
                topic=classification.get("topic", ""),
            )
            interaction.confidence_score = pubmed.confidence_score
            # persiste citações verificadas
            for c in pubmed.cited_guidelines_verified:
                if c.pmid:
                    self.db.add(PubmedValidation(
                        interaction_id=interaction.id,
                        pmid=c.pmid,
                        article_title=c.title,
                        abstract_snippet=None,
                        relevance_score=1.0 if c.verified else 0.0,
                    ))
            # persiste guidelines novas (pós-cutoff)
            for a in pubmed.newer_guidelines_found:
                self.db.add(PubmedValidation(
                    interaction_id=interaction.id,
                    pmid=a.pmid,
                    article_title=a.article_title,
                    abstract_snippet=a.abstract_snippet or None,
                    relevance_score=0.0,
                ))

            # 11. Audit log
            audit = AuditLog(
                user_id=self.user_id,
                interaction_id=interaction.id,
                action="orquestrador_query",
                entity_type="interaction",
                entity_id=interaction.id,
                metadata_={
                    "mode": mode,
                    "triage_confidence": confidence,
                    "model_used": agent_response.get("model_id", "pharmadb"),
                    "is_fallback": agent_response.get("is_fallback", False),
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

            return_dict = {
                "status": "ok",
                "cache_hit": False,
                "interaction_id": str(interaction.id),
                "conversation_id": str(conv_id),
                "mode": mode,
                "triage_confidence": confidence,
                "model_used": agent_response.get("model_id", "pharmadb"),
                "is_fallback": agent_response.get("is_fallback", False),
                "response_text": agent_response.get("text", ""),
                "tokens_in": agent_response.get("tokens_in"),
                "tokens_out": agent_response.get("tokens_out"),
                "cost_usd": float(cost),
                "specialty_detected": classification["specialty"],
                "topic_detected": classification["topic"],
                "confidence_score": pubmed.confidence_score,
                "low_evidence_alert": pubmed.low_evidence_alert,
                "outdated_alert": pubmed.outdated_alert,
                "cited_guidelines_verified": [
                    {
                        "title": c.title,
                        "pmid": c.pmid,
                        "verified": c.verified,
                    }
                    for c in pubmed.cited_guidelines_verified
                ],
                "newer_guidelines_found": [
                    {
                        "pmid": a.pmid,
                        "title": a.article_title,
                    }
                    for a in pubmed.newer_guidelines_found
                ],
                "total_response_time_ms": elapsed_ms,
                "disclaimer": DISCLAIMER_RESPOSTA,
            }

            # 12. Armazenar no cache semântico (apenas se não fallback e temos embedding)
            if (
                mode in {"QUICK_SEARCH", "CLINICAL_REASONING"}
                and not agent_response.get("is_fallback")
                and _cache_embedding
                and _cache_normalized
            ):
                await store_response(self.db, mode, _cache_normalized, _cache_embedding, return_dict)

            return return_dict

        except Exception as e:
            logger.error(f"ERRO NO ORQUESTRADOR: {e}")
            traceback.print_exc()
            raise

# ── Agente de IA ─────────────────────────────────────────

    async def _handle_ai_agent(self, mode: str, prompt: str) -> dict:
        model_id = MODE_MODEL_MAP[mode]
        system_prompt = MODE_PROMPT_MAP[mode]

        result = await self.db.execute(
            select(ModelPricing).where(
                ModelPricing.model_id == model_id,
                ModelPricing.status == True,
            )
        )
        model_info = result.scalar_one_or_none()

        if not model_info:
            return {"text": f"Modelo {model_id} não disponível.", "error": "model_not_found"}

        provider = get_provider_by_type(model_info.provider_type)
        temperature = MODE_TEMPERATURE_MAP.get(mode, 1.0)  # ← fora do try, não precisa estar dentro

        try:
            response = await provider.complete(
                model_id, prompt, system_prompt=system_prompt, temperature=temperature
            )
            return {
                "text": response.text,
                "model_id": model_id,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "is_fallback": False,
            }
        except Exception as e:
            logger.warning(f"Falha no {model_id}: {e}. Tentando fallback...")
            return await self._try_fallback(mode, prompt, system_prompt, str(e))

    # ── Fallback ─────────────────────────────────────────────

    async def _try_fallback(self, mode: str, prompt: str, system_prompt: str, original_error: str) -> dict:
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
                    "is_fallback": True,
                }
            except Exception:
                continue

        return {
            "text": "Desculpe, não foi possível processar sua consulta no momento. Tente novamente em instantes.",
            "error": original_error,
            "is_fallback": True,
        }

    # ── PHARMA_CHECK ─────────────────────────────────────────

    async def _handle_pharma_check(self, prompt: str, interaction_id) -> dict:
        from app.services.pharmadb_service import get_pharmadb_service
        from app.services.medication_extractor import extract_medications

        pharmadb = get_pharmadb_service()

        meds = await extract_medications(prompt)
        nomes = [m.get("normalized") or m.get("raw", "") for m in meds]

        if len(nomes) < 2:
            return {
                "text": "⚠️ Preciso de pelo menos 2 medicamentos para checar interações. Reformule sua pergunta incluindo os medicamentos que deseja verificar.",
                "model_id": "pharmadb",
                "is_fallback": False,
            }

        resultado = await pharmadb.checar_interacoes(nomes)

        for alerta in resultado.get("interacoes", []):
            self.db.add(PharmaAlert(
                interaction_id=interaction_id,
                alert_level=alerta["semaforo_level"],
                alert_color=alerta["semaforo_color"],
                description=f"{alerta['pa_a']} ↔ {alerta['pa_b']}: {alerta['efeito_clinico']}",
                source_api="pharmadb",
            ))

        texto = pharmadb.formatar_resposta_texto(resultado)

        return {
            "text": texto,
            "model_id": "pharmadb",
            "is_fallback": False,
        }

    # ── Conversation ─────────────────────────────────────────

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