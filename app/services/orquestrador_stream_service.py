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
from app.core.telemetry import (
    get_current_span,
    set_llm_cost,
    traced_interaction_stream,
)
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import (
    Interaction,
    InteractionResponse,
)
from app.services.integracoes.ai_providers import get_provider_by_type
from app.services.orquestrador_modes import (
    EFFORT_MAX_TOKENS,
    FALLBACK_MODELS,
    GREETING_REPLY,
    MODE_MODEL_MAP,
    MODE_TEMPERATURE_MAP,
    PHARMA_MODES,
)
from app.services.orquestrador_shared import (
    MENSAGEM_PRECISA_REFINAR,
    check_clarification,
    decidir_rota,
    ensure_conversation,
    link_attachments,
    load_context_messages,
    pode_usar_cache,
    pos_processar_interacao,
    registrar_hit_de_cache,
    resolve_clarification_prompt,
)
from app.services.pricing import calcular_custo_ferramentas, calculate_cost, get_model_pricing
from app.services.response_metadata import build_response_metadata
from app.services.semantic_cache_service import get_cached_response, store_response
from app.services.triage_service import is_off_topic_greeting
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

    @traced_interaction_stream()
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
                # 2c+3. Histórico e roteamento EM PARALELO.
                #
                # `decidir_rota` chama a triagem (uma ida ao gpt-5.4-nano, ~400-900ms
                # quando não está no cache do Redis) e recebe apenas prompt, modo e a
                # flag de anexo — não depende do histórico. `load_context_messages`
                # faz queries e, dentro de pasta, um embedding na OpenAI (~150-400ms).
                #
                # Eram sequenciais sem motivo: o tempo de um era somado ao do outro
                # antes do primeiro token. Medição em produção mostrou p50 de 33s em
                # CLINICAL_REASONING, e todo o `asyncio.gather` do arquivo estava no
                # pós-processamento — que já não bloqueia nada.
                #
                # As regras de roteamento são compartilhadas com o /query
                # (`orquestrador_shared.decidir_rota`); aqui muda só a forma de
                # comunicar: evento SSE em vez de corpo de resposta.
                history_messages, decisao = await asyncio.gather(
                    load_context_messages(
                        db, self.user_id, conversation_id,
                        pergunta_atual=sanitized_prompt, folder_id=folder_id,
                    ),
                    decidir_rota(sanitized_prompt, mode, bool(attachment_ids)),
                )
                mode, confidence = decisao.mode, decisao.confidence

                if decisao.precisa_refinar:
                    yield _sse("error", {
                        "status": "needs_refinement",
                        "message": MENSAGEM_PRECISA_REFINAR,
                    })
                    return

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
                # Conversa com material de paciente no contexto NÃO usa cache —
                # nem lê, nem grava. Ver `contexto_tem_dado_de_paciente`: a
                # chave do cache é `(modo, prompt)`, mas a resposta foi gerada
                # com a evolução da pasta junto.
                pode_cachear = pode_usar_cache(mode, history_messages)
                if pode_cachear:
                    cached, _cache_normalized, _cache_embedding = await get_cached_response(
                        db, mode, sanitized_prompt
                    )
                    if cached is not None:
                        # A resposta do cache TAMBÉM entra no histórico, e os
                        # ids devolvidos precisam ser os DESTE usuário — o
                        # cache é global por modo. Ver `registrar_hit_de_cache`.
                        conv_id, cached_interaction = await registrar_hit_de_cache(
                            db,
                            user_id=self.user_id,
                            company_id=self.company_id,
                            conversation_id=conversation_id,
                            folder_id=folder_id,
                            mode=mode,
                            sanitized_prompt=sanitized_prompt,
                            prompt_sanitizado=dlp_result.was_sanitized,
                            confidence=confidence,
                            cached=cached,
                        )
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
                # Consumo de ferramentas integradas (Data Ocean), que só chega
                # no token final do stream.
                tool_usage: dict | None = None
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
                            tool_usage = token.tool_usage

                except Exception as e:
                    # `type(e).__name__` junto da mensagem: um `httpx.ReadTimeout`
                    # tem `str()` VAZIO, e o log saía como "Stream falhou em
                    # sabia-4-thinking: ." — sem dizer que a causa era timeout.
                    # Foi assim que o Data Ocean falhou em produção sem deixar
                    # pista nenhuma.
                    logger.warning(
                        "Stream falhou em %s: %s: %s. Tentando fallback completo...",
                        model_id, type(e).__name__, e or "(sem mensagem)",
                    )
                    is_fallback = True
                    fallback_result = await self._fallback_complete(
                        db,
                        mode,
                        sanitized_prompt,
                        system_prompt,
                        history=history_messages,
                        image_content=image_content,
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
                    # Ferramentas integradas (Data Ocean) cobram por GB, busca
                    # e minuto — grandezas que `calculate_cost` não vê.
                    cost += calcular_custo_ferramentas(tool_usage)

                # O custo REAL vai para o trace aqui, e nao no provider: quando
                # ele retorna, este numero ainda nao existe. Sem isto o Phoenix
                # estimava o custo por tokens — o que para o DATA_OCEAN e
                # simplesmente errado, ja que o custo dele esta em GB e minutos.
                # Ver `set_llm_cost`.
                set_llm_cost(
                    get_current_span(),
                    cost_usd=cost,
                    tool_usage=tool_usage,
                    mode=mode,
                )

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

                # 8. Pós-processamento: especialidade, medicamentos e PubMed
                # em paralelo, e a persistência do que apuram. Vive no shared
                # porque o `/query` faz exatamente o mesmo — ver
                # `pos_processar_interacao`.
                pos = await pos_processar_interacao(
                    db, interaction, sanitized_prompt, full_text, mode,
                )
                classification, medications, pubmed = (
                    pos.classification, pos.medications, pos.pubmed,
                )

                # Referências junto da resposta. Sem isto elas só existiam no
                # evento SSE `done` e sumiam ao reabrir a conversa — o "as
                # referências se perdem no histórico" relatado.
                ir.extra_metadata = build_response_metadata(
                    pubmed=pubmed,
                    citations=perplexity_citations,
                    tool_usage=tool_usage,
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

                # Store no cache.
                #
                # `pode_cachear` no lugar do literal de modos que estava aqui:
                # a lista duplicada divergiria de `MODOS_CACHEAVEIS`, e o gate
                # de contexto de paciente precisa valer na GRAVAÇÃO também —
                # senão a resposta condicionada entra no cache e vaza na
                # próxima leitura de outro médico.
                if (
                    pode_cachear
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
        self,
        db,
        mode: str,
        prompt: str,
        system_prompt: str,
        history: list[dict] | None = None,
        image_content: dict | list | None = None,
    ) -> dict:
        """Cadeia de fallback do modo, quando o streaming do primário falha.

        `image_content` é repassado: sem isso, uma leitura de exame que caísse
        no fallback perdia a imagem e o modelo secundário respondia sobre um
        exame que nunca recebeu — sem que o médico soubesse.
        """
        candidatos = FALLBACK_MODELS.get(mode, [])
        if not candidatos:
            # Ausência de fallback é decisão, não esquecimento: no DATA_OCEAN
            # nenhum outro modelo consulta as bases brasileiras, e responder da
            # memória de treino entregaria números inventados com a mesma cara
            # de uma consulta real. Mas o log precisa dizer isso, senão a falha
            # parece defeito de configuração.
            logger.warning(
                "Modo %s não tem fallback declarado — a falha do modelo "
                "primário será devolvida ao médico.", mode,
            )

        for fallback_model in candidatos:
            model_info = await get_model_pricing(db, fallback_model)
            if not model_info:
                continue
            try:
                provider = get_provider_by_type(model_info.provider_type)
                response = await provider.complete(
                    fallback_model,
                    prompt,
                    system_prompt=system_prompt,
                    history=history,
                    image_content=image_content,
                )
                return {
                    "text": response.text,
                    "model_id": fallback_model,
                    "tokens_in": response.tokens_in,
                    "tokens_out": response.tokens_out,
                }
            except Exception as e:
                # Sem isto, a falha de CADA modelo da cadeia desaparecia: o log
                # tinha só o aviso do primário, e não havia como diagnosticar
                # "por que a resposta saiu genérica" sem reproduzir.
                logger.warning(
                    "Fallback %s também falhou: %s: %s",
                    fallback_model, type(e).__name__, e or "(sem mensagem)",
                )
                continue
        return {
            "text": "Desculpe, não foi possível processar sua consulta no momento.",
            "model_id": MODE_MODEL_MAP.get(mode, "unknown"),
            "tokens_in": None,
            "tokens_out": None,
        }

