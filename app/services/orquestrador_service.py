"""
Médico 360 — Serviço do Orquestrador Multi-Agente.
Pipeline: Triagem → Roteamento → Agente Especializado → Resposta.
"""

import asyncio
import inspect
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.prompts import (
    DISCLAIMER_RESPOSTA,
    build_orquestrador_prompt,
)
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import (
    Interaction,
    InteractionMedication,
    InteractionResponse,
    ModelPricing,
    PharmaAlert,
    PubmedValidation,
)
from app.schemas.agregador import ConversationMessage
from app.services.ai_providers import get_provider_by_type
from app.services.medication_extractor import extract_from_interaction
from app.services.orquestrador_modes import (
    GREETING_REPLY,
    MODE_MODEL_MAP,
    MODE_TEMPERATURE_MAP,
    PHARMA_CHECK_MIN_CONFIDENCE,
    PHARMA_MODES,
)
from app.services.orquestrador_shared import (
    build_enriched_prompt,
    check_clarification,
    ensure_conversation,
    resolve_clarification_prompt,
)
from app.services.pricing import calculate_cost
from app.services.pubmed_service import validate_with_pubmed
from app.services.response_metadata import build_response_metadata
from app.services.semantic_cache_service import get_cached_response, store_response
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.triage_service import is_off_topic_greeting, triage
from app.services.usage_service import add_interaction_audit

logger = logging.getLogger(__name__)


# Configuração por modo PharmaDB: (método de busca, método de formatação, rótulo).
# Os três fluxos compartilham a mesma lógica — só mudam essas três peças.
PHARMA_MODE_CONFIG = {
    "PHARMA_BULA": ("buscar_bula", "formatar_bula", "bula"),
    "PHARMA_RECEITA": ("buscar_receita", "formatar_receita", "receituário"),
    "PHARMA_GENERICO": ("buscar_genericos", "formatar_genericos", "genéricos"),
}



class OrquestradorService:
    """Serviço principal do Orquestrador Multi-Agente."""

    def __init__(self, db: AsyncSession, user_id: UUID, company_id: UUID | None = None,
                 user_specialty: str | None = None, user_med_status: str | None = None):
        self.db = db
        self.user_id = user_id
        self.company_id = company_id
        self.user_specialty = user_specialty
        self.user_med_status = user_med_status

    async def query(
        self,
        prompt: str,
        conversation_id: UUID | None = None,
        force: bool = False,
        clarification_answers: str | None = None,
        mode: str | None = None,
        history: list[ConversationMessage] | None = None,
        folder_id: UUID | None = None,
        image_content: dict | None = None,
    ) -> dict:
        try:
            start_time = time.monotonic()

            # 1. Resolução de prompt: se há respostas de clarificação, monta contexto completo
            if clarification_answers and conversation_id:
                prompt = await resolve_clarification_prompt(self.db, self.user_id, conversation_id, clarification_answers)

            # 2. DLP
            dlp_result = await sanitize_prompt_async(prompt)
            sanitized_prompt = dlp_result.sanitized_text

            # 2a. Saudação / mensagem sem conteúdo clínico — atalho local, sem
            # gastar chamada de modelo. O streaming já tratava; aqui não, e a
            # triagem PODE devolver OFF_TOPIC: o modo caía em _handle_ai_agent,
            # onde MODE_MODEL_MAP["OFF_TOPIC"] estourava KeyError e o médico
            # recebia erro interno por ter dito "bom dia".
            if is_off_topic_greeting(sanitized_prompt):
                return await self._responder_saudacao(
                    conversation_id, sanitized_prompt, dlp_result, folder_id, start_time
                )

            # 2b. Enriquecer prompt com histórico
            enriched_prompt = build_enriched_prompt(sanitized_prompt, history)

            # 3. Triagem
            # Quando o frontend manda PHARMA_CHECK explícito, ainda rodamos triage
            # para descobrir o sub-modo correto (bula, receita, genérico, interação),
            # mas ignoramos o gate de confiança baixa — o usuário já escolheu o modo.
            explicit_pharma = (mode == "PHARMA_CHECK")
            if mode and not explicit_pharma:
                confidence = 1.0
            else:
                triage_result = await triage(sanitized_prompt)
                mode = triage_result["mode"]
                confidence = triage_result["confidence"]

                if confidence < 0.7 and not explicit_pharma:
                    return {
                        "status": "needs_refinement",
                        "mode": mode,
                        "confidence": confidence,
                        "message": "Preciso de um pouco mais de aprofundamento para te indicar o agente correto. Pode reformular com mais detalhes?",
                        "disclaimer": DISCLAIMER_RESPOSTA,
                    }

                if mode == "PHARMA_CHECK" and confidence < PHARMA_CHECK_MIN_CONFIDENCE:
                    mode = "CLINICAL_REASONING" if not explicit_pharma else "PHARMA_CHECK"

                if mode in PHARMA_MODES and mode != "PHARMA_CHECK" and confidence < PHARMA_CHECK_MIN_CONFIDENCE and not explicit_pharma:
                    mode = "QUICK_SEARCH"

            # 4. Clarification check (apenas CLINICAL_REASONING, sem force, sem answers)
            if mode == "CLINICAL_REASONING" and not force and not clarification_answers:
                clarification = await check_clarification(sanitized_prompt)
                if not clarification.get("sufficient", True):
                    questions = clarification.get("questions", [])
                    conv_id = await ensure_conversation(self.db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id)
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
                        started_at=datetime.now(UTC),
                    )
                    self.db.add(pending)
                    await self.db.flush()
                    return {
                        "status": "clarification_needed",
                        "conversation_id": str(conv_id),
                        "questions": questions,
                    }

            # 5. Cache semântico (apenas modos clínicos)
            _cache_normalized: str = ""
            _cache_embedding: list = []
            if mode in {"QUICK_SEARCH", "CLINICAL_REASONING"}:
                cached, _cache_normalized, _cache_embedding = await get_cached_response(
                    self.db, mode, sanitized_prompt
                )
                if cached is not None:
                    return {**cached, "cache_hit": True}

            # 4. Conversation
            conv_id = await ensure_conversation(self.db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id)

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
                started_at=datetime.now(UTC),
            )
            self.db.add(interaction)
            await self.db.flush()

            # 5. Roteamento pro agente
            if mode == "PHARMA_CHECK":
                agent_response = await self._handle_pharma_check(enriched_prompt, interaction.id)
            elif mode in PHARMA_MODE_CONFIG:
                agent_response = await self._handle_pharma(enriched_prompt, mode)
            else:
                agent_response = await self._handle_ai_agent(mode, enriched_prompt, image_content=image_content)

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
            interaction.completed_at = datetime.now(UTC)

            # 8-10. Pós-processamento independente em paralelo: especialidade/tema,
            # medicamentos e validação PubMed (apenas modos clínicos; timeout 15s com
            # fallback). O PubMed usa o próprio texto da resposta como fallback de tópico.
            response_texts = [agent_response.get("text", "")]
            classification, medications, pubmed = await asyncio.gather(
                detect_specialty_and_topic(sanitized_prompt),
                extract_from_interaction(sanitized_prompt, response_texts),
                validate_with_pubmed(
                    agent_response=agent_response.get("text", ""),
                    mode=mode,
                    topic="",
                ),
            )

            interaction.specialty_detected = classification["specialty"]
            interaction.topic_detected = classification["topic"]

            for med in medications:
                self.db.add(InteractionMedication(
                    interaction_id=interaction.id,
                    medication_raw=med["medication_raw"],
                    medication_normalized=med["medication_normalized"],
                    source=med["source"],
                ))

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

            # Referências junto da resposta, para sobreviverem ao reload.
            # `citations` vem só do caminho de streaming (Perplexity); aqui
            # normalmente é None e o helper simplesmente as omite.
            ir.extra_metadata = build_response_metadata(
                pubmed=pubmed,
                citations=agent_response.get("citations"),
            )

            # 11. Audit log
            add_interaction_audit(
                self.db,
                user_id=self.user_id,
                interaction_id=interaction.id,
                action="orquestrador_query",
                metadata={
                    "mode": mode,
                    "triage_confidence": confidence,
                    "model_used": agent_response.get("model_id", "pharmadb"),
                    "is_fallback": agent_response.get("is_fallback", False),
                    "prompt_length": len(prompt),
                    "total_cost_usd": str(cost),
                    "dlp_sanitized": dlp_result.was_sanitized,
                    "dlp_replacements": dlp_result.replacement_count,
                    "dlp_by_type": dlp_result.counts_by_type,
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
                await store_response(
                    self.db, mode, _cache_normalized, _cache_embedding, return_dict,
                    raw_prompt=sanitized_prompt,
                )

            return return_dict

        except Exception as e:
            logger.exception("ERRO NO ORQUESTRADOR: %s", e)
            raise

# ── Agente de IA ─────────────────────────────────────────

    async def _handle_ai_agent(self, mode: str, prompt: str, image_content: dict | None = None) -> dict:
        model_id = MODE_MODEL_MAP[mode]
        system_prompt = build_orquestrador_prompt(mode, self.user_specialty, self.user_med_status)

        result = await self.db.execute(
            select(ModelPricing).where(
                ModelPricing.model_id == model_id,
                ModelPricing.status.is_(True),
            )
        )
        model_info = result.scalar_one_or_none()

        if not model_info:
            return {"text": f"Modelo {model_id} não disponível.", "error": "model_not_found"}

        provider = get_provider_by_type(model_info.provider_type)
        temperature = MODE_TEMPERATURE_MAP.get(mode, 1.0)

        try:
            response = await provider.complete(
                model_id, prompt, system_prompt=system_prompt, temperature=temperature, image_content=image_content
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
                    ModelPricing.status.is_(True),
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
        from app.services.medication_extractor import extract_medications
        from app.services.pharmadb_service import get_pharmadb_service

        pharmadb = get_pharmadb_service()

        meds = await extract_medications(prompt)
        # Usa normalized (genérico) para busca de PA
        nomes = [m.get("normalized") or m.get("raw", "") for m in meds if m.get("normalized") or m.get("raw")]

        if len(nomes) < 2:
            return {
                "text": "⚠️ Preciso de pelo menos 2 medicamentos para checar interações. Reformule sua pergunta incluindo os medicamentos que deseja verificar.",
                "model_id": "pharmadb",
                "is_fallback": False,
            }

        try:
            resultado = await pharmadb.checar_interacoes(nomes)
        except Exception as e:
            logger.warning(f"PharmaDB indisponível, caindo para CLINICAL_REASONING: {e}")
            aviso = (
                "⚠️ *A checagem automática de interações está temporariamente indisponível.* "
                "Segue análise clínica com base no conhecimento do modelo:\n\n"
            )
            fallback = await self._handle_ai_agent("CLINICAL_REASONING", prompt)
            fallback["text"] = aviso + fallback.get("text", "")
            fallback["is_fallback"] = True
            return fallback

        for alerta in resultado.get("interacoes", []):
            self.db.add(PharmaAlert(
                interaction_id=interaction_id,
                alert_level=alerta["semaforo_level"],
                alert_color=alerta["semaforo_color"],
                description=f"{alerta['pa_a']} ↔ {alerta['pa_b']}: {alerta['efeito_clinico']}",
                source_api="pharmadb",
            ))

        texto = pharmadb.formatar_interacoes(resultado)

        return {
            "text": texto,
            "model_id": "pharmadb",
            "is_fallback": False,
        }

    async def _extrair_nome_medicamento(self, prompt: str) -> tuple[str | None, str | None]:
        """Retorna (raw, normalized) do primeiro medicamento extraído do prompt."""
        from app.services.medication_extractor import extract_medications
        meds = await extract_medications(prompt)
        if not meds:
            return None, None
        return meds[0].get("raw") or "", meds[0].get("normalized") or ""

    async def _buscar_com_fallback(self, buscar_fn, raw: str, normalized: str):
        """Tenta buscar pelo raw; se não achar, tenta pelo normalized."""
        resultado = await buscar_fn(raw)
        if resultado is None and normalized and normalized.lower() != raw.lower():
            resultado = await buscar_fn(normalized)
        return resultado

    # ── PHARMA_BULA / RECEITA / GENERICO ──────────────────────

    async def _handle_pharma(self, prompt: str, mode: str) -> dict:
        """
        Fluxo único para os modos PharmaDB baseados em medicamento
        (bula/receita/genérico). As diferenças por modo vêm de PHARMA_MODE_CONFIG.
        """
        from app.services.pharmadb_service import get_pharmadb_service

        pharmadb = get_pharmadb_service()
        buscar_attr, formatar_attr, label = PHARMA_MODE_CONFIG[mode]

        raw, normalized = await self._extrair_nome_medicamento(prompt)
        if not raw and not normalized:
            return {
                "text": "⚠️ Não identifiquei o nome do medicamento na sua pergunta. Por favor, informe o nome do produto.",
                "model_id": "pharmadb",
                "is_fallback": False,
            }

        try:
            resultado = await self._buscar_com_fallback(
                getattr(pharmadb, buscar_attr), raw, normalized
            )
        except Exception as e:
            logger.warning("PharmaDB %s indisponível: %s", label, e)
            return await self._pharma_fallback(prompt)

        if not resultado:
            msg = await pharmadb.mensagem_nao_encontrado(raw or normalized, label)
            return {"text": msg, "model_id": "pharmadb", "is_fallback": False}

        # formatar_bula é async; formatar_receita/genericos são síncronos.
        formatado = getattr(pharmadb, formatar_attr)(resultado)
        if inspect.isawaitable(formatado):
            formatado = await formatado

        return {"text": formatado, "model_id": "pharmadb", "is_fallback": False}

    async def _pharma_fallback(self, prompt: str) -> dict:
        aviso = (
            "⚠️ *A base PharmaDB está temporariamente indisponível.* "
            "Segue análise com base no conhecimento do modelo:\n\n"
        )
        fallback = await self._handle_ai_agent("QUICK_SEARCH", prompt)
        fallback["text"] = aviso + fallback.get("text", "")
        fallback["is_fallback"] = True
        return fallback

    # Clarificação e resolução de conversa vivem em `orquestrador_shared`:
    # eram idênticas às do serviço de streaming, com `self.db` como única
    # diferença.

    async def _responder_saudacao(
        self, conversation_id, sanitized_prompt: str, dlp_result, folder_id, start_time: float
    ) -> dict:
        """Espelha o atalho de saudação do streaming, para os dois responderem igual."""
        conv_id = await ensure_conversation(
            self.db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id
        )
        interaction = Interaction(
            conversation_id=conv_id,
            user_id=self.user_id,
            company_id=self.company_id,
            feature="ORQUESTRADOR",
            mode="OFF_TOPIC",
            prompt_text=sanitized_prompt,
            prompt_sanitized=dlp_result.was_sanitized,
            triage_confidence=1.0,
            triage_category="OFF_TOPIC",
            cache_hit=False,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        self.db.add(interaction)
        await self.db.flush()
        self.db.add(InteractionResponse(
            interaction_id=interaction.id,
            model_used="off_topic_shortcut",
            response_text=GREETING_REPLY,
        ))
        await self.db.flush()

        return {
            "status": "ok",
            "cache_hit": False,
            "interaction_id": str(interaction.id),
            "conversation_id": str(conv_id),
            "mode": "OFF_TOPIC",
            "triage_confidence": 1.0,
            "model_used": "off_topic_shortcut",
            "is_fallback": False,
            "response_text": GREETING_REPLY,
            "tokens_in": None,
            "tokens_out": None,
            "cost_usd": 0.0,
            "total_response_time_ms": int((time.monotonic() - start_time) * 1000),
            "disclaimer": DISCLAIMER_RESPOSTA,
        }