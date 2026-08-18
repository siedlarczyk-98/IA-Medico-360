"""
Médico 360 — Serviço do Agregador de IA.
Implementa RN-AGR-001 a RN-AGR-004.
Chamadas concorrentes a múltiplos providers com auditoria completa.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.prompts import DISCLAIMER_RESPOSTA
from app.services.pubmed_service import validate_with_pubmed
from app.schemas.agregador import PubmedValidationResult, VerifiedCitationOut, PubMedArticleOut
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import (
    Conversation,
    Interaction,
    InteractionMedication,
    InteractionResponse,
)
from app.schemas.agregador import (
    AgregadorRequest,
    AgregadorResponse,
    ModelResponse,
)
from app.services.ai_providers import ProviderResponse, get_provider_by_type
from app.services.medication_extractor import extract_from_interaction
from app.services.pricing import Pricing, calculate_cost, get_model_pricing
from app.services.usage_service import add_interaction_audit, record_cost
from app.services.specialty_detector import detect_specialty_and_topic

logger = logging.getLogger(__name__)


def _make_title(prompt: str) -> str:
    """Gera título de conversa a partir do prompt, removendo prefixos de arquivo injetados."""
    if prompt.startswith('[Imagem:'):
        prompt = prompt.split('\n\n', 1)[-1] if '\n\n' in prompt else prompt
    elif '---\n\n' in prompt:
        prompt = prompt.split('---\n\n', 1)[1]
    return prompt[:100] + ('...' if len(prompt) > 100 else '')


class AgregadorService:
    """Serviço principal do Agregador de IA."""

    def __init__(self, db: AsyncSession, user_id: UUID, company_id: UUID | None = None):
        self.db = db
        self.user_id = user_id
        self.company_id = company_id

    # ── Consulta principal (non-streaming) ───────────────────

    async def query(self, request: AgregadorRequest, system_prompt: str | None = None) -> AgregadorResponse:
        """
        Executa consulta no Agregador:
        1. Sanitiza prompt via DLP
        2. Cria/recupera conversa
        3. Registra interação
        4. Busca modelos no banco
        5. Chama providers em paralelo
        6. Salva respostas + custo  → commit (dados essenciais garantidos)
        7. Detecta especialidade + tema  (best-effort)
        8. Extrai medicamentos  (best-effort)
        9. Audit log
        """
        start_time = time.monotonic()

        # 1. DLP
        dlp_result = await sanitize_prompt_async(request.prompt)
        sanitized_prompt = dlp_result.sanitized_text

        # 2. Conversation (usa prompt sanitizado no título)
        conversation_id = await self._ensure_conversation(
            request.conversation_id, sanitized_prompt
        )

        # 3. Interaction
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

        # 4. Modelos
        models_info = await self._get_models_info(request.models)

        # 5. Providers em paralelo
        model_responses = await self._call_providers(
            prompt=sanitized_prompt,
            models_info=models_info,
            system_prompt=system_prompt,
        )

        # 6. Respostas + custo
        total_cost = Decimal("0")
        response_models: list[ModelResponse] = []
        # Guarda objetos ir e citations antes do commit para evitar lazy-load após expiração
        ir_by_model: dict[str, InteractionResponse] = {}
        citations_by_model: dict[str, list] = {}

        for model_id, result in model_responses.items():
            if isinstance(result, ProviderResponse):
                citations = result.citations or []
                cost = await calculate_cost(self.db, model_id, result.tokens_in, result.tokens_out)
                ir = InteractionResponse(
                    interaction_id=interaction.id,
                    model_used=model_id,
                    response_text=result.text,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    cost_usd=cost,
                    extra_metadata={"citations": citations} if citations else None,
                    is_fallback=False,
                )
                self.db.add(ir)
                ir_by_model[model_id] = ir
                citations_by_model[model_id] = citations
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

        await record_cost(self.db, self.user_id, total_cost)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        interaction.response_time_ms = elapsed_ms
        interaction.token_cost_usd = total_cost
        interaction.completed_at = datetime.now(timezone.utc)
        await self.db.flush()

        # Commit cedo — dados essenciais garantidos mesmo que enriquecimento falhe
        await self.db.commit()

        # 7-9. Enriquecimento best-effort (falha aqui não perde a interação)
        classification = {"specialty": None, "topic": None}
        medications: list[dict] = []
        pubmed_by_model: dict[str, PubmedValidationResult] = {}
        try:
            classification = await detect_specialty_and_topic(sanitized_prompt)
            interaction.specialty_detected = classification["specialty"]
            interaction.topic_detected = classification["topic"]

            # Validação PubMed — só para respostas clínicas com texto
            is_clinical = classification["specialty"] not in (None, "Cotidiano/Não clínico")
            if is_clinical:
                clinical_tasks = {
                    rm.model_id: validate_with_pubmed(
                        agent_response=rm.response_text,
                        mode="CLINICAL_REASONING",
                        topic=classification.get("topic", ""),
                    )
                    for rm in response_models
                    if rm.response_text and not rm.error
                }
                if clinical_tasks:
                    pub_results = await asyncio.gather(*clinical_tasks.values(), return_exceptions=True)
                    for mid, val in zip(clinical_tasks.keys(), pub_results):
                        if isinstance(val, Exception):
                            logger.warning(f"PubMed validation falhou para {mid}: {val}")
                            continue
                        # Só processa se não for fallback e tiver citações verificadas ou guidelines
                        verified = [c for c in val.cited_guidelines_verified if c.verified]
                        if val.fallback or (not verified and not val.newer_guidelines_found):
                            continue
                        pubmed_schema = PubmedValidationResult(
                            cited_guidelines_verified=[
                                VerifiedCitationOut(title=c.title, pmid=c.pmid, verified=c.verified)
                                for c in verified
                            ],
                            newer_guidelines_found=[
                                PubMedArticleOut(
                                    pmid=a.pmid,
                                    article_title=a.article_title,
                                    abstract_snippet=a.abstract_snippet,
                                )
                                for a in val.newer_guidelines_found
                            ],
                            fallback=val.fallback,
                        )
                        pubmed_by_model[mid] = pubmed_schema
                        # Atualiza extra_metadata no banco (cita citations já em memória)
                        existing_citations = citations_by_model.get(mid, [])
                        meta: dict = {}
                        if existing_citations:
                            meta["citations"] = existing_citations
                        meta["pubmed"] = pubmed_schema.model_dump()
                        ir_by_model[mid].extra_metadata = meta

            response_texts = [r.response_text for r in response_models if r.response_text]
            medications = await extract_from_interaction(sanitized_prompt, response_texts)
            for med in medications:
                self.db.add(InteractionMedication(
                    interaction_id=interaction.id,
                    medication_raw=med["medication_raw"],
                    medication_normalized=med["medication_normalized"],
                    source=med["source"],
                ))

            add_interaction_audit(
                self.db,
                user_id=self.user_id,
                interaction_id=interaction.id,
                action="agregador_query",
                metadata={
                    "models": request.models,
                    "prompt_length": len(request.prompt),
                    "response_count": len(response_models),
                    "total_cost_usd": str(total_cost),
                    "dlp_sanitized": dlp_result.was_sanitized,
                    "dlp_replacements": dlp_result.replacement_count,
                    "specialty_detected": classification["specialty"],
                    "topic_detected": classification["topic"],
                    "medications": [m["medication_normalized"] for m in medications],
                    "pubmed_validated": list(pubmed_by_model.keys()),
                },
            )
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Enriquecimento pós-query falhou (interação já salva): {e}")

        # Incorpora pubmed_validation nos ModelResponse
        final_responses = [
            rm.model_copy(update={"pubmed_validation": pubmed_by_model.get(rm.model_id)})
            for rm in response_models
        ]

        return AgregadorResponse(
            interaction_id=interaction.id,
            conversation_id=conversation_id,
            responses=final_responses,
            disclaimer=DISCLAIMER_RESPOSTA,
            total_response_time_ms=elapsed_ms,
            created_at=interaction.created_at,
            specialty_detected=classification["specialty"],
            topic_detected=classification["topic"],
        )

    # ── Salvar interação após streaming ─────────────────────

    async def save_stream_interaction(
        self,
        conversation_id: UUID,
        sanitized_prompt: str,
        prompt_sanitized: bool,
        collected: dict[str, dict],
        elapsed_ms: int,
    ) -> tuple[UUID, dict[str, PubmedValidationResult]]:
        """Persiste interação + respostas coletadas durante o stream."""
        interaction = Interaction(
            conversation_id=conversation_id,
            user_id=self.user_id,
            company_id=self.company_id,
            feature="AGREGADOR",
            mode=None,
            prompt_text=sanitized_prompt,
            prompt_sanitized=prompt_sanitized,
            cache_hit=False,
            response_time_ms=elapsed_ms,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(interaction)
        await self.db.flush()

        total_cost = Decimal("0")
        ir_by_model: dict[str, InteractionResponse] = {}
        citations_by_model: dict[str, list] = {}
        for model_id, data in collected.items():
            if data.get("error"):
                ir = InteractionResponse(
                    interaction_id=interaction.id,
                    model_used=model_id,
                    response_text="",
                    error_message=data["error"],
                    is_fallback=False,
                )
            else:
                citations = data.get("citations") or []
                cost = await calculate_cost(
                    self.db, model_id, data.get("tokens_in"), data.get("tokens_out")
                )
                cost += Decimal(str(data.get("search_cost_usd", 0.0)))
                total_cost += cost
                ir = InteractionResponse(
                    interaction_id=interaction.id,
                    model_used=model_id,
                    response_text=data.get("text", ""),
                    tokens_in=data.get("tokens_in"),
                    tokens_out=data.get("tokens_out"),
                    cost_usd=cost,
                    extra_metadata={"citations": citations} if citations else None,
                    is_fallback=False,
                )
                ir_by_model[model_id] = ir
                citations_by_model[model_id] = citations
            self.db.add(ir)

        interaction.token_cost_usd = total_cost
        await record_cost(self.db, self.user_id, total_cost)
        await self.db.flush()

        # Commit cedo — dados essenciais garantidos
        await self.db.commit()

        # Enriquecimento best-effort
        pubmed_by_model: dict[str, PubmedValidationResult] = {}
        try:
            classification = await detect_specialty_and_topic(sanitized_prompt)
            interaction.specialty_detected = classification["specialty"]
            interaction.topic_detected = classification["topic"]

            # Validação PubMed — só para respostas clínicas com texto
            is_clinical = classification["specialty"] not in (None, "Cotidiano/Não clínico")
            if is_clinical:
                clinical_tasks = {
                    mid: validate_with_pubmed(
                        agent_response=data["text"],
                        mode="CLINICAL_REASONING",
                        topic=classification.get("topic", ""),
                    )
                    for mid, data in collected.items()
                    if data.get("text") and not data.get("error")
                }
                if clinical_tasks:
                    pub_results = await asyncio.gather(*clinical_tasks.values(), return_exceptions=True)
                    for mid, val in zip(clinical_tasks.keys(), pub_results):
                        if isinstance(val, Exception):
                            logger.warning(f"PubMed validation falhou para {mid}: {val}")
                            continue
                        verified = [c for c in val.cited_guidelines_verified if c.verified]
                        if val.fallback or (not verified and not val.newer_guidelines_found):
                            continue
                        pubmed_schema = PubmedValidationResult(
                            cited_guidelines_verified=[
                                VerifiedCitationOut(title=c.title, pmid=c.pmid, verified=c.verified)
                                for c in verified
                            ],
                            newer_guidelines_found=[
                                PubMedArticleOut(
                                    pmid=a.pmid,
                                    article_title=a.article_title,
                                    abstract_snippet=a.abstract_snippet,
                                )
                                for a in val.newer_guidelines_found
                            ],
                            fallback=val.fallback,
                        )
                        pubmed_by_model[mid] = pubmed_schema
                        if mid in ir_by_model:
                            existing_citations = citations_by_model.get(mid, [])
                            meta: dict = {}
                            if existing_citations:
                                meta["citations"] = existing_citations
                            meta["pubmed"] = pubmed_schema.model_dump()
                            ir_by_model[mid].extra_metadata = meta

            response_texts = [d.get("text", "") for d in collected.values() if d.get("text")]
            medications = await extract_from_interaction(sanitized_prompt, response_texts)
            for med in medications:
                self.db.add(InteractionMedication(
                    interaction_id=interaction.id,
                    medication_raw=med["medication_raw"],
                    medication_normalized=med["medication_normalized"],
                    source=med["source"],
                ))

            add_interaction_audit(
                self.db,
                user_id=self.user_id,
                interaction_id=interaction.id,
                action="agregador_stream",
                metadata={
                    "models": list(collected.keys()),
                    "prompt_length": len(sanitized_prompt),
                    "response_count": len([d for d in collected.values() if not d.get("error")]),
                    "total_cost_usd": str(total_cost),
                    "pubmed_validated": list(pubmed_by_model.keys()),
                },
            )
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Enriquecimento pós-stream falhou (interação já salva): {e}")

        return interaction.id, pubmed_by_model

    # ── Buscar info dos modelos no banco ─────────────────────

    async def _get_models_info(self, model_ids: list[str]) -> dict[str, Pricing]:
        """Busca provider_type e info de cada modelo (com cache em memória TTL 1h)."""
        results = await asyncio.gather(
            *[get_model_pricing(self.db, mid) for mid in model_ids]
        )
        found = {mid: info for mid, info in zip(model_ids, results) if info is not None}
        missing = [mid for mid, info in zip(model_ids, results) if info is None]
        if missing:
            logger.warning(f"Modelos não encontrados em model_pricing (serão ignorados): {missing}")
        return found

    # ── Chamadas paralelas aos providers ─────────────────────

    async def _call_providers(
        self,
        prompt: str,
        models_info: dict[str, Pricing],
        system_prompt: str | None = None,
    ) -> dict[str, ProviderResponse | Exception]:
        """
        RN-AGR-001: Se um modelo falhar, não impacta os demais.
        Busca o provider pelo tipo e passa o model_id dinâmico.
        """
        tasks = {}
        for model_id, model_info in models_info.items():
            provider = get_provider_by_type(model_info.provider_type)
            tasks[model_id] = provider.complete(model_id, prompt, system_prompt=system_prompt)

        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True,
        )

        return dict(zip(tasks.keys(), results))

    # ── Conversation management ──────────────────────────────

    async def _ensure_conversation(
        self, conversation_id: UUID | None, sanitized_prompt: str, folder_id: UUID | None = None
    ) -> UUID:
        """Cria nova conversa ou valida existente. Usa prompt já sanitizado no título."""
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

        title = _make_title(sanitized_prompt)
        conv = Conversation(
            user_id=self.user_id,
            title=title,
            feature="AGREGADOR",
            folder_id=folder_id,
        )
        self.db.add(conv)
        await self.db.flush()
        return conv.id

    # ── Contexto de conversa para streaming ─────────────────

    async def get_conversation_context(self, conversation_id: UUID, limit: int = 5) -> str:
        """
        Retorna as últimas N interações da conversa formatadas como contexto.
        Inclui prompt do médico e primeira resposta de cada interação.
        """
        stmt = (
            select(Interaction)
            .options(selectinload(Interaction.responses))
            .where(
                Interaction.conversation_id == conversation_id,
                Interaction.feature == "AGREGADOR",
            )
            .order_by(Interaction.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        interactions = list(reversed(result.scalars().all()))

        if not interactions:
            return ""

        parts = ["[Conversa anterior]"]
        for inter in interactions:
            parts.append(f"Médico: {inter.prompt_text}")
            for resp in inter.responses[:1]:  # primeira resposta disponível
                if resp.response_text:
                    parts.append(f"Assistente ({resp.model_used}): {resp.response_text[:800]}")
        parts.append("[Pergunta atual]")
        return "\n".join(parts) + "\n"

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
            .order_by(Interaction.created_at.desc())
        )

        if query:
            stmt = stmt.where(Interaction.prompt_text.ilike(f"%{query}%"))
        if date_from:
            stmt = stmt.where(Interaction.created_at >= date_from)
        if date_to:
            stmt = stmt.where(Interaction.created_at <= date_to)
        if model_filter:
            stmt = stmt.where(
                Interaction.responses.any(
                    InteractionResponse.model_used == model_filter
                )
            )
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())