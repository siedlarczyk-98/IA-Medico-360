"""
Médico 360 — Serviço do Agregador de IA.
Implementa RN-AGR-001 a RN-AGR-004.
Chamadas concorrentes a múltiplos providers com auditoria completa.
"""

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.citacoes_fonte import normalizar as normalizar_citacoes
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import (
    Conversation,
    Interaction,
    InteractionMedication,
    InteractionResponse,
)
from app.schemas.agregador import (
    PubMedArticleOut,
    PubmedValidationResult,
    VerifiedCitationOut,
)
from app.services.integracoes.pubmed_service import validate_with_pubmed
from app.services.medication_extractor import extract_from_interaction
from app.services.orquestrador_shared import make_title
from app.services.pricing import Pricing, calculate_cost, get_model_pricing
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.usage_service import add_interaction_audit, record_cost

logger = logging.getLogger(__name__)

ERRO_DE_MODELO_PARA_O_CLIENTE = "Falha ao consultar este modelo. Tente novamente."


class AgregadorService:
    """Serviço principal do Agregador de IA."""

    def __init__(self, db: AsyncSession, user_id: UUID, company_id: UUID | None = None):
        self.db = db
        self.user_id = user_id
        self.company_id = company_id

    # ── Consulta principal (non-streaming) ───────────────────


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
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
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
                citations = normalizar_citacoes(data.get("citations"))
                cost = await calculate_cost(
                    self.db, model_id, data.get("tokens_in"), data.get("tokens_out")
                )
                cost += Decimal(str(data.get("search_cost_usd", 0.0)))
                total_cost += cost
                # DLP NA RESPOSTA DO MODELO, antes de gravar. Só o `query()` — a rota
                # que ninguém chamava — fazia isto; este caminho, o que está em uso,
                # gravava o texto cru. Um modelo que repete na resposta o nome e o
                # CPF que o médico digitou deixava o dado do paciente no histórico,
                # apesar de o PROMPT ter sido mascarado. Mesma regra do stream do
                # orquestrador: na tela saiu o original, no banco fica a versão
                # mascarada. `use_ner=False`: ver `sanitize_prompt_async`.
                texto = data.get("text", "")
                if texto:
                    texto = (await sanitize_prompt_async(texto, use_ner=False)).sanitized_text
                ir = InteractionResponse(
                    interaction_id=interaction.id,
                    model_used=model_id,
                    response_text=texto,
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

        title = make_title(sanitized_prompt)
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


    # ── Histórico (RN-AGR-004) ───────────────────────────────
