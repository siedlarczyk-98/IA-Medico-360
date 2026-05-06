"""
Médico 360 — Serviço do Agregador de IA.
Implementa RN-AGR-001 a RN-AGR-004.
Chamadas concorrentes a múltiplos providers com auditoria completa.
"""

import asyncio
import logging
import time
import traceback
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.prompts import DISCLAIMER_RESPOSTA
from app.middleware.dlp import sanitize_prompt
from app.models.models import (
    AuditLog,
    Conversation,
    Interaction,
    InteractionMedication,
    InteractionResponse,
    ModelPricing,
)
from app.schemas.agregador import (
    AgregadorRequest,
    AgregadorResponse,
    ModelResponse,
)
from app.services.ai_providers import ProviderResponse, get_provider_by_type
from app.services.medication_extractor import extract_from_interaction
from app.services.pricing import calculate_cost
from app.services.specialty_detector import detect_specialty_and_topic

logger = logging.getLogger(__name__)


class AgregadorService:
    """Serviço principal do Agregador de IA."""

    def __init__(self, db: AsyncSession, user_id: UUID, company_id: UUID | None = None):
        self.db = db
        self.user_id = user_id
        self.company_id = company_id

    # ── Consulta principal (non-streaming) ───────────────────

    async def query(self, request: AgregadorRequest) -> AgregadorResponse:
        """
        Executa consulta no Agregador:
        1. Sanitiza prompt via DLP
        2. Cria/recupera conversa
        3. Registra interação
        4. Busca modelos no banco
        5. Chama providers em paralelo
        6. Salva respostas + auditoria
        7. Detecta especialidade + tema
        8. Extrai medicamentos
        9. Audit log
        """
        try:
            start_time = time.monotonic()

            # 1. DLP: sanitizar prompt antes de enviar para APIs externas
            dlp_result = sanitize_prompt(request.prompt)
            sanitized_prompt = dlp_result.sanitized_text

            # 2. Conversation
            conversation_id = await self._ensure_conversation(
                request.conversation_id, request.prompt
            )

            # 3. Interaction (salva prompt SANITIZADO no banco)
            interaction = Interaction(
                conversation_id=conversation_id,
                user_id=self.user_id,
                company_id=self.company_id,
                feature="AGREGADOR",
                mode=None,
                prompt_text=sanitized_prompt,
                prompt_sanitized=dlp_result.was_sanitized,
                cache_hit=False,
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(interaction)
            await self.db.flush()

            # 4. Buscar modelos no banco pra saber o provider_type
            models_info = await self._get_models_info(request.models)

            # 5. Chamadas concorrentes aos providers
            model_responses = await self._call_providers(
                prompt=sanitized_prompt,
                models_info=models_info,
            )

            # 6. Salvar respostas no banco
            total_cost = Decimal("0")
            response_models: list[ModelResponse] = []

            for model_id, result in model_responses.items():
                if isinstance(result, ProviderResponse):
                    cost = await calculate_cost(self.db, model_id, result.tokens_in, result.tokens_out)

                    ir = InteractionResponse(
                        interaction_id=interaction.id,
                        model_used=model_id,
                        response_text=result.text,
                        response_time_ms=None,
                        tokens_in=result.tokens_in,
                        tokens_out=result.tokens_out,
                        cost_usd=cost,
                        is_fallback=False,
                    )
                    self.db.add(ir)
                    total_cost += cost

                    response_models.append(
                        ModelResponse(
                            model_id=model_id,
                            provider=result.provider,
                            response_text=result.text,
                            response_time_ms=0,
                            tokens_in=result.tokens_in,
                            tokens_out=result.tokens_out,
                            cost_usd=float(cost),
                        )
                    )
                else:
                    error_msg = str(result)
                    ir = InteractionResponse(
                        interaction_id=interaction.id,
                        model_used=model_id,
                        response_text="",
                        error_message=error_msg,
                        is_fallback=False,
                    )
                    self.db.add(ir)

                    response_models.append(
                        ModelResponse(
                            model_id=model_id,
                            provider="",
                            response_text="",
                            response_time_ms=0,
                            error=error_msg,
                        )
                    )

            # 7. Finalizar interaction
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            interaction.response_time_ms = elapsed_ms
            interaction.token_cost_usd = total_cost
            interaction.completed_at = datetime.now(timezone.utc)

            # 8. Detectar especialidade e tema via IA
            classification = await detect_specialty_and_topic(sanitized_prompt)
            interaction.specialty_detected = classification["specialty"]
            interaction.topic_detected = classification["topic"]

            # 9. Extrair medicamentos mencionados
            response_texts = [r.response_text for r in response_models if r.response_text]
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
                action="agregador_query",
                entity_type="interaction",
                entity_id=interaction.id,
                metadata_={
                    "models": request.models,
                    "prompt_length": len(request.prompt),
                    "response_count": len(response_models),
                    "total_cost_usd": str(total_cost),
                    "dlp_sanitized": dlp_result.was_sanitized,
                    "dlp_replacements": dlp_result.replacement_count,
                    "specialty_detected": classification["specialty"],
                    "topic_detected": classification["topic"],
                    "medications": [m["medication_normalized"] for m in medications],
                },
            )
            self.db.add(audit)
            await self.db.flush()

            return AgregadorResponse(
                interaction_id=interaction.id,
                conversation_id=conversation_id,
                responses=response_models,
                disclaimer=DISCLAIMER_RESPOSTA,
                total_response_time_ms=elapsed_ms,
                created_at=interaction.createdat,
                specialty_detected=classification["specialty"],
                topic_detected=classification["topic"],
            )

        except Exception as e:
            logger.error(f"ERRO NO AGREGADOR QUERY: {e}")
            traceback.print_exc()
            raise

    # ── Buscar info dos modelos no banco ─────────────────────

    async def _get_models_info(self, model_ids: list[str]) -> dict[str, ModelPricing]:
        """Busca provider_type e info de cada modelo no banco."""
        result = await self.db.execute(
            select(ModelPricing).where(
                ModelPricing.model_id.in_(model_ids),
                ModelPricing.status == True,
            )
        )
        models = result.scalars().all()
        return {m.model_id: m for m in models}

    # ── Chamadas paralelas aos providers ─────────────────────

    async def _call_providers(
        self,
        prompt: str,
        models_info: dict[str, ModelPricing],
    ) -> dict[str, ProviderResponse | Exception]:
        """
        RN-AGR-001: Se um modelo falhar, não impacta os demais.
        Busca o provider pelo tipo e passa o model_id dinâmico.
        """
        tasks = {}
        for model_id, model_info in models_info.items():
            provider = get_provider_by_type(model_info.provider_type)
            tasks[model_id] = provider.complete(model_id, prompt)

        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        return dict(zip(tasks.keys(), results))

    # ── Conversation management ──────────────────────────────

    async def _ensure_conversation(
        self, conversation_id: UUID | None, prompt: str
    ) -> UUID:
        """Cria nova conversa ou valida existente."""
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
            feature="AGREGADOR",
        )
        self.db.add(conv)
        await self.db.flush()
        return conv.id

    # ── Histórico (RN-AGR-004) ───────────────────────────────

    async def get_history(
        self,
        query: str | None = None,
        model_filter: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Interaction]:
        """
        RN-AGR-004: histórico pesquisável por data, modelo e palavras-chave.
        Retenção mínima: 12 meses.
        """
        stmt = (
            select(Interaction)
            .options(selectinload(Interaction.responses))
            .where(
                Interaction.user_id == self.user_id,
                Interaction.feature == "AGREGADOR",
            )
            .order_by(Interaction.createdat.desc())
        )

        if query:
            stmt = stmt.where(Interaction.prompt_text.ilike(f"%{query}%"))
        if date_from:
            stmt = stmt.where(Interaction.createdat >= date_from)
        if date_to:
            stmt = stmt.where(Interaction.createdat <= date_to)
        if model_filter:
            stmt = stmt.where(
                Interaction.responses.any(
                    InteractionResponse.model_used == model_filter
                )
            )
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())