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
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.prompts import (
    DISCLAIMER_RESPOSTA,
    build_orquestrador_prompt,
)
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import (
    Interaction,
    InteractionMedication,
    InteractionResponse,
    PubmedValidation,
)
from app.services.ai_providers import get_provider_by_type
from app.services.medication_extractor import extract_from_interaction
from app.services.orquestrador_modes import (
    EFFORT_MAX_TOKENS,
    FALLBACK_MODELS,
    GREETING_REPLY,
    MODE_MODEL_MAP,
    MODE_TEMPERATURE_MAP,
    MODOS_CACHEAVEIS,
    PHARMA_CHECK_MIN_CONFIDENCE,
    PHARMA_MODES,
    upgrade_mode_for_attachments,
)
from app.services.orquestrador_shared import (
    check_clarification,
    ensure_conversation,
    link_attachments,
    load_context_messages,
    resolve_clarification_prompt,
)
from app.services.pricing import calculate_cost, get_model_pricing
from app.services.pubmed_service import validate_with_pubmed
from app.services.response_metadata import build_metadata_from_cached, build_response_metadata
from app.services.semantic_cache_service import get_cached_response, store_response
from app.services.specialty_detector import detect_specialty_and_topic
from app.services.triage_service import is_off_topic_greeting, triage
from app.services.usage_service import add_interaction_audit, record_cost

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class OrquestradorStreamService:

    def __init__(self, session_factory: async_sessionmaker, user_id: UUID, company_id: UUID | None = None,
                 user_specialty: str | None = None, user_med_status: str | None = None):
        self.session_factory = session_factory
        self.user_id = user_id
        self.company_id = company_id
        self.user_specialty = user_specialty
        self.user_med_status = user_med_status

    async def stream(
        self,
        prompt: str,
        conversation_id: UUID | None = None,
        force: bool = False,
        clarification_answers: str | None = None,
        effort: str = "detalhado",
        mode: str | None = None,
        folder_id: UUID | None = None,
        image_content: dict | list | None = None,
        attachment_ids: list | None = None,
    ) -> AsyncIterator[str]:
        """
        Gerador SSE. Yields strings no formato 'event: ...\ndata: ...\n\n'.

        Eventos emitidos:
          - start        → modo e confiança da triagem
          - cache_hit    → resposta completa cacheada (encerra stream)
          - token        → fragmento de texto do modelo
          - text_done    → texto completo na tela; o cliente já pode liberar
                           a digitação. O que falta depois disto é metadado.
          - done         → metadados finais (PubMed, custo, etc.)
          - error        → erro fatal
        """
        start_time = time.monotonic()

        async with self.session_factory() as db:
            try:
                # 1. Resolução de prompt: se há respostas de clarificação, monta contexto completo
                if clarification_answers and conversation_id:
                    prompt = await resolve_clarification_prompt(
                        db, self.user_id, conversation_id, clarification_answers
                    )

                # 2. DLP
                dlp_result = await sanitize_prompt_async(prompt)
                sanitized_prompt = dlp_result.sanitized_text

                # 2a. Saudação / mensagem sem conteúdo clínico — atalho local, sem
                # gastar uma chamada de modelo. Independe do modo selecionado na UI,
                # já que um modo explícito pula a triagem automática (ver item 3).
                if is_off_topic_greeting(sanitized_prompt):
                    conv_id = await ensure_conversation(db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id)
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
                    db.add(interaction)
                    await db.flush()
                    db.add(InteractionResponse(
                        interaction_id=interaction.id,
                        model_used="off_topic_shortcut",
                        response_text=GREETING_REPLY,
                    ))
                    await db.commit()

                    yield _sse("start", {"mode": "OFF_TOPIC", "triage_confidence": 1.0})
                    yield _sse("token", {"text": GREETING_REPLY})
                    yield _sse("done", {
                        "interaction_id": str(interaction.id),
                        "conversation_id": str(conv_id),
                        "mode": "OFF_TOPIC",
                        "model_used": "off_topic_shortcut",
                        "is_fallback": False,
                        "tokens_in": None,
                        "tokens_out": None,
                        "cost_usd": 0.0,
                        "total_response_time_ms": int((time.monotonic() - start_time) * 1000),
                        "disclaimer": DISCLAIMER_RESPOSTA,
                    })
                    return

                # 2b. Histórico: lido do BANCO, não do que o cliente mandou.
                # O parâmetro `history` da requisição é ignorado de propósito —
                # ver `conversation_history.load_history`. O cache continua
                # usando `sanitized_prompt`, sem histórico.
                history_messages = await load_context_messages(db, self.user_id, conversation_id, pergunta_atual=sanitized_prompt, folder_id=folder_id)

                # 3. Triage — PHARMA_CHECK explícito ainda passa pelo triage para
                # resolver o sub-modo correto (bula, receita, genérico, interação),
                # mas ignora o gate de confiança baixa — o usuário já escolheu o modo.
                # Anexo presente promove raciocinio clinico para leitura de exame.
                mode = upgrade_mode_for_attachments(mode, bool(attachment_ids))

                explicit_pharma = (mode == "PHARMA_CHECK")
                if mode and not explicit_pharma:
                    confidence = 1.0
                else:
                    triage_result = await triage(sanitized_prompt)
                    mode = triage_result["mode"]
                    confidence = triage_result["confidence"]

                    if confidence < 0.7 and not explicit_pharma:
                        yield _sse("error", {
                            "status": "needs_refinement",
                            "message": "Preciso de um pouco mais de aprofundamento. Pode reformular com mais detalhes?",
                        })
                        return

                    if mode == "PHARMA_CHECK" and confidence < PHARMA_CHECK_MIN_CONFIDENCE:
                        mode = "CLINICAL_REASONING" if not explicit_pharma else "PHARMA_CHECK"

                    if mode in PHARMA_MODES and mode != "PHARMA_CHECK" and confidence < PHARMA_CHECK_MIN_CONFIDENCE and not explicit_pharma:
                        mode = "QUICK_SEARCH"

                if mode in PHARMA_MODES:
                    yield _sse("error", {
                        "status": "unsupported_mode",
                        "message": "Modos PharmaDB não suportam streaming. Use /query.",
                    })
                    return

                # 4. Clarification check (apenas CLINICAL_REASONING, sem force, sem answers)
                if mode == "CLINICAL_REASONING" and not force and not clarification_answers:
                    clarification = await check_clarification(sanitized_prompt, contexto=history_messages)
                    if not clarification.get("sufficient", True):
                        questions = clarification.get("questions", [])
                        conv_id = await ensure_conversation(db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id)
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
                if mode in MODOS_CACHEAVEIS:
                    cached, _cache_normalized, _cache_embedding = await get_cached_response(
                        db, mode, sanitized_prompt
                    )
                    if cached is not None:
                        # A resposta do cache TAMBÉM entra no histórico. Antes
                        # este caminho retornava aqui, sem criar conversa nem
                        # interação: a mensagem inteira sumia do histórico, não
                        # só as referências.
                        conv_id = await ensure_conversation(
                            db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id
                        )
                        cached_interaction = Interaction(
                            conversation_id=conv_id,
                            user_id=self.user_id,
                            company_id=self.company_id,
                            feature="ORQUESTRADOR",
                            mode=mode,
                            prompt_text=sanitized_prompt,
                            prompt_sanitized=dlp_result.was_sanitized,
                            triage_confidence=confidence,
                            triage_category=mode,
                            cache_hit=True,
                            confidence_score=cached.get("confidence_score"),
                            specialty_detected=cached.get("specialty_detected"),
                            topic_detected=cached.get("topic_detected"),
                            started_at=datetime.now(UTC),
                            completed_at=datetime.now(UTC),
                        )
                        db.add(cached_interaction)
                        await db.flush()
                        db.add(InteractionResponse(
                            interaction_id=cached_interaction.id,
                            model_used=cached.get("model_used") or "cache",
                            response_text=cached.get("response_text") or "",
                            cost_usd=Decimal("0"),
                            extra_metadata=build_metadata_from_cached(cached),
                        ))
                        await db.commit()

                        # Os ids do payload são os da interação que POPULOU o
                        # cache — de outro usuário, já que o cache é global por
                        # modo. Devolvê-los faria o cliente apontar para uma
                        # conversa que não é dele.
                        yield _sse("cache_hit", {
                            **cached,
                            "cache_hit": True,
                            "conversation_id": str(conv_id),
                            "interaction_id": str(cached_interaction.id),
                        })
                        return

                # 4. Conversation + Interaction
                conv_id = await ensure_conversation(db, self.user_id, conversation_id, sanitized_prompt, folder_id=folder_id)
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
                db.add(interaction)
                await db.flush()
                await link_attachments(db, self.user_id, interaction.id, attachment_ids)

                # 5. Streaming do modelo
                model_id = MODE_MODEL_MAP.get(mode)
                system_prompt = build_orquestrador_prompt(mode, self.user_specialty, self.user_med_status)
                if effort == "rápido" and system_prompt:
                    system_prompt = "Responda de forma direta e concisa, foco nos pontos essenciais.\n\n" + system_prompt
                temperature = MODE_TEMPERATURE_MAP.get(mode, 1.0)
                max_tokens = EFFORT_MAX_TOKENS.get(effort, 4096)

                model_info = await get_model_pricing(db, model_id)

                if not model_info:
                    yield _sse("error", {"message": f"Modelo {model_id} não disponível."})
                    return

                provider = get_provider_by_type(model_info.provider_type)

                full_text = ""
                tokens_in: int | None = None
                tokens_out: int | None = None
                perplexity_citations: list[str] | None = None
                is_fallback = False

                try:
                    async for token in provider.stream(
                        model_id,
                        sanitized_prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        image_content=image_content,
                        max_tokens=max_tokens,
                        history=history_messages,
                    ):
                        if token.delta:
                            full_text += token.delta
                            yield _sse("token", {"text": token.delta})
                        if token.done:
                            tokens_in = token.tokens_in
                            tokens_out = token.tokens_out
                            perplexity_citations = token.citations

                except Exception as e:
                    logger.warning(f"Stream falhou em {model_id}: {e}. Tentando fallback completo...")
                    is_fallback = True
                    fallback_result = await self._fallback_complete(
                        db, mode, sanitized_prompt, system_prompt, history=history_messages
                    )
                    full_text = fallback_result.get("text", "")
                    tokens_in = fallback_result.get("tokens_in")
                    tokens_out = fallback_result.get("tokens_out")
                    model_id = fallback_result.get("model_id", model_id)
                    yield _sse("token", {"text": full_text})

                # 6. Persistência da resposta
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
                interaction.completed_at = datetime.now(UTC)

                # A auditoria nasce aqui, com o que já se sabe. Deixá-la só no
                # commit final abriria um buraco de LGPD: um abort durante o
                # PubMed apagaria o registro de que a interação existiu.
                audit_base = {
                    "mode": mode,
                    "triage_confidence": confidence,
                    "model_used": model_id,
                    "is_fallback": is_fallback,
                    "prompt_length": len(prompt),
                    "total_cost_usd": str(cost),
                    "dlp_sanitized": dlp_result.was_sanitized,
                    "dlp_replacements": dlp_result.replacement_count,
                    "dlp_by_type": dlp_result.counts_by_type,
                }
                audit = add_interaction_audit(
                    db,
                    user_id=self.user_id,
                    interaction_id=interaction.id,
                    action="orquestrador_stream",
                    metadata=audit_base,
                )

                await record_cost(db, self.user_id, cost)

                # Commit de durabilidade, e ele precisa vir ANTES do `text_done`.
                # A partir desse evento o cliente reabilita a digitação, e mandar
                # outra pergunta aborta este SSE — cancelando a corrotina no meio
                # do `gather` abaixo. Com um commit só no fim, o abort levava
                # junto a resposta inteira: o médico via o texto na tela e não o
                # encontrava mais ao reabrir a conversa. O custo entra aqui pelo
                # mesmo motivo: consumo cobrado não pode depender do PubMed.
                await db.commit()

                # 7. Texto entregue. Tudo daqui para baixo é metadado e custa
                # segundos de rede; o cliente não deve esperar por isso para
                # deixar o médico escrever de novo.
                yield _sse("text_done", {
                    "conversation_id": str(conv_id),
                    "mode": mode,
                    "model_used": model_id,
                    "is_fallback": is_fallback,
                })

                # 8. Pós-processamento independente roda em paralelo (specialty, meds, PubMed)
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

                # Referências junto da resposta. Sem isto elas só existiam no
                # evento SSE `done` e sumiam ao reabrir a conversa — o "as
                # referências se perdem no histórico" relatado.
                ir.extra_metadata = build_response_metadata(
                    pubmed=pubmed,
                    citations=perplexity_citations,
                )

                # Reatribuição, e não mutação in-place: a coluna é JSON comum,
                # sem MutableDict, e um `audit.metadata_[...] = x` não marcaria
                # o objeto como sujo — o enriquecimento sumiria no commit.
                audit.metadata_ = {
                    **audit_base,
                    "specialty_detected": classification["specialty"],
                    "topic_detected": classification["topic"],
                    "medications": [m["medication_normalized"] for m in medications],
                    "pubmed_confidence_score": pubmed.confidence_score,
                    "pubmed_low_evidence_alert": pubmed.low_evidence_alert,
                    "pubmed_outdated_alert": pubmed.outdated_alert,
                    "pubmed_fallback": pubmed.fallback,
                    "pubmed_cited_verified": sum(1 for c in pubmed.cited_guidelines_verified if c.verified),
                    "pubmed_newer_found": len(pubmed.newer_guidelines_found),
                }

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
                        # Sem esta chave, quem recebesse a resposta pelo cache
                        # a veria sem fontes — a original tem, a cacheada não.
                        "citations": perplexity_citations,
                    }
                    await store_response(
                        db, mode, _cache_normalized, _cache_embedding, done_payload,
                        raw_prompt=sanitized_prompt,
                    )

                # 9. Segundo commit: só os metadados (especialidade, medicamentos,
                # PubMed, auditoria). Se ele não acontecer, a resposta já está
                # salva pelo commit anterior.
                await db.commit()

                # 10. Evento final
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
                    "citations": perplexity_citations,
                })

            except Exception as e:
                logger.error(f"ERRO NO STREAM: {e}")
                await db.rollback()
                yield _sse("error", {"message": "Erro interno. Tente novamente."})

    async def _fallback_complete(
        self, db, mode: str, prompt: str, system_prompt: str, history: list[dict] | None = None
    ) -> dict:
        for fallback_model in FALLBACK_MODELS.get(mode, []):
            model_info = await get_model_pricing(db, fallback_model)
            if not model_info:
                continue
            try:
                provider = get_provider_by_type(model_info.provider_type)
                response = await provider.complete(fallback_model, prompt, system_prompt=system_prompt, history=history)
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

