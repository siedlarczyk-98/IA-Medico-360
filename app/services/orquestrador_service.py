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
from app.models.models import PharmaAlert
from app.middleware.dlp import sanitize_prompt
from app.models.models import (
    AuditLog,
    Conversation,
    Interaction,
    InteractionMedication,
    InteractionResponse,
    ModelPricing,
)
from app.services.ai_providers import get_provider_by_type
from app.services.medication_extractor import extract_from_interaction
from app.services.pricing import calculate_cost
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.triage_service import triage

logger = logging.getLogger(__name__)

# Mapeamento modo → model_id padrão
MODE_MODEL_MAP = {
    "QUICK_SEARCH": "sonar-pro",
    "CLINICAL_REASONING": "claude-sonnet-4-20250514",
    "PHARMA_CHECK": None,
    "PRODUCTIVITY": "gpt-5.4-nano",
}

# Mapeamento modo → system prompt
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
        """
        Pipeline completo do Orquestrador:
        1. DLP
        2. Triagem
        3. Roteamento
        4. Resposta do agente
        5. Auditoria completa
        """
        try:
            start_time = time.monotonic()

            # 1. DLP
            dlp_result = sanitize_prompt(prompt)
            sanitized_prompt = dlp_result.sanitized_text

            # 2. Triagem (The Gatekeeper)
            triage_result = await triage(sanitized_prompt)
            mode = triage_result["mode"]
            confidence = triage_result["confidence"]

            # Se confiança baixa, pedir refinamento
            if confidence < 0.7:
                return {
                    "status": "needs_refinement",
                    "mode": mode,
                    "confidence": confidence,
                    "message": "Preciso de um pouco mais de aprofundamento para te indicar o agente correto. Pode reformular com mais detalhes?",
                    "disclaimer": DISCLAIMER_RESPOSTA,
                }

            # 3. Conversation
            conv_id = await self._ensure_conversation(conversation_id, prompt)

            # 4. Interaction
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
            if agent_response.get("model_id"):
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

            # 10. Audit log
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
                },
            )
            self.db.add(audit)
            await self.db.flush()

            return {
                "status": "ok",
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
                "total_response_time_ms": elapsed_ms,
                "disclaimer": DISCLAIMER_RESPOSTA,
            }

        except Exception as e:
            logger.error(f"ERRO NO ORQUESTRADOR: {e}")
            traceback.print_exc()
            raise

    # ── Agente de IA (QUICK_SEARCH, CLINICAL_REASONING, PRODUCTIVITY) ──

    async def _handle_ai_agent(self, mode: str, prompt: str) -> dict:
        """Chama o modelo de IA correto pro modo, com fallback."""
        model_id = MODE_MODEL_MAP[mode]
        system_prompt = MODE_PROMPT_MAP[mode]

        # Buscar provider no banco
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

        try:
            response = await provider.complete(model_id, prompt, system_prompt=system_prompt)
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
        """Tenta modelos alternativos em caso de falha."""
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

    # ── PHARMA_CHECK (PharmaDB) ──────────────────────────────

async def _handle_pharma_check(self, prompt: str, interaction_id) -> dict:
        """Checagem farmacológica via PharmaDB."""
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

        # Salvar pharma_alerts
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