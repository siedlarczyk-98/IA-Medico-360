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

from app.core.database import async_session_factory
from app.core.prompts import (
    DISCLAIMER_RESPOSTA,
    build_orquestrador_prompt,
)
from app.core.telemetry import get_current_span, set_llm_cost, traced_interaction
from app.middleware.dlp import sanitize_prompt_async
from app.models.models import (
    Interaction,
    InteractionResponse,
    ModelPricing,
    PharmaAlert,
)
from app.services.integracoes.ai_providers import get_provider_by_type
from app.services.orquestrador_modes import (
    FALLBACK_MODELS,
    GREETING_REPLY,
    MODE_MODEL_MAP,
    MODE_TEMPERATURE_MAP,
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
from app.services.pricing import calcular_custo_ferramentas, calculate_cost
from app.services.response_metadata import build_response_metadata
from app.services.semantic_cache_service import get_cached_response, store_response
from app.services.triage_service import is_off_topic_greeting
from app.services.usage_service import add_interaction_audit, record_cost

logger = logging.getLogger(__name__)


# Referência forte às tarefas de pós-processamento em voo. `asyncio` só guarda
# referência fraca, então sem este conjunto o coletor de lixo pode recolher a
# tarefa no meio — e a falha seria silenciosa. Mesmo motivo de
# `folder_context_service._indexacoes_em_voo`.
_pos_em_voo: set[asyncio.Task] = set()


async def _pos_processar_em_background(
    *,
    user_id: UUID,
    interaction_id: UUID,
    response_id: UUID,
    audit_id: UUID,
    audit_base: dict,
    sanitized_prompt: str,
    texto_resposta: str,
    mode: str,
    citations,
    tool_usage,
    cachear: bool,
    cache_normalized,
    cache_embedding,
    payload_base: dict,
) -> None:
    """
    Roda o pós-processamento fora da requisição, com sessão própria.

    A sessão da requisição NÃO pode ser reaproveitada: `AsyncSession` não é
    segura para uso concorrente e a requisição já terá dado commit e retornado.
    Por isso os objetos ORM são recarregados por id aqui dentro — passar as
    instâncias da outra sessão daria `DetachedInstanceError` ou, pior, escrita
    numa transação que esta função não controla.
    """
    from app.models.models import AuditLog

    async with async_session_factory() as db:
        try:
            interaction = await db.get(Interaction, interaction_id)
            ir = await db.get(InteractionResponse, response_id)
            if interaction is None or ir is None:  # pragma: no cover
                logger.warning(
                    "[PosProcessamento] Interação %s sumiu antes do pós-processamento",
                    interaction_id,
                )
                return

            pos = await pos_processar_interacao(
                db, interaction, sanitized_prompt, texto_resposta, mode,
            )
            classification, medications, pubmed = (
                pos.classification, pos.medications, pos.pubmed,
            )

            # Referências junto da resposta, para sobreviverem ao reload.
            ir.extra_metadata = build_response_metadata(
                pubmed=pubmed,
                citations=citations,
                tool_usage=tool_usage,
            )

            # Reatribuição, e não mutação in-place: a coluna é JSON comum, sem
            # MutableDict, e um `audit.metadata_[...] = x` não marcaria o objeto
            # como sujo — o enriquecimento sumiria no commit.
            audit = await db.get(AuditLog, audit_id)
            if audit is not None:
                audit.metadata_ = {
                    **audit_base,
                    "specialty_detected": classification["specialty"],
                    "topic_detected": classification["topic"],
                    "medications": [m["medication_normalized"] for m in medications],
                    "pubmed_confidence_score": pubmed.confidence_score,
                    "pubmed_low_evidence_alert": pubmed.low_evidence_alert,
                    "pubmed_outdated_alert": pubmed.outdated_alert,
                    "pubmed_fallback": pubmed.fallback,
                    "pubmed_cited_verified": sum(
                        1 for c in pubmed.cited_guidelines_verified if c.verified
                    ),
                    "pubmed_newer_found": len(pubmed.newer_guidelines_found),
                }

            # O cache só é gravado AGORA, com o payload completo. Cachear antes
            # serviria a outro médico uma resposta sem validação PubMed — e é do
            # cache que o `cache_hit` do front tira o bloco de referências.
            if cachear:
                payload = {
                    **payload_base,
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
                }
                await store_response(
                    db, mode, cache_normalized, cache_embedding, payload,
                    raw_prompt=sanitized_prompt,
                )

            await db.commit()
        except Exception:
            await db.rollback()
            raise


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

    @traced_interaction()
    async def query(
        self,
        prompt: str,
        conversation_id: UUID | None = None,
        force: bool = False,
        clarification_answers: str | None = None,
        mode: str | None = None,
        folder_id: UUID | None = None,
        image_content: dict | list | None = None,
        attachment_ids: list | None = None,
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

            # 2b+3. Histórico e roteamento EM PARALELO.
            #
            # O histórico vem do BANCO, não do que o cliente mandou — o parâmetro
            # `history` da requisição é ignorado de propósito, ver
            # `conversation_history.load_history`.
            #
            # `decidir_rota` chama a triagem (uma ida ao gpt-5.4-nano) e recebe
            # só prompt, modo e a flag de anexo: não depende do histórico. Eram
            # sequenciais sem motivo, somando os dois tempos antes de responder.
            #
            # As regras de roteamento são compartilhadas com o /stream
            # (`orquestrador_shared.decidir_rota`): só a forma de comunicar o
            # pedido de reformulação muda entre os dois.
            history_messages, decisao = await asyncio.gather(
                load_context_messages(
                    self.db, self.user_id, conversation_id,
                    pergunta_atual=sanitized_prompt, folder_id=folder_id,
                ),
                decidir_rota(sanitized_prompt, mode, bool(attachment_ids)),
            )
            mode, confidence = decisao.mode, decisao.confidence

            if decisao.precisa_refinar:
                return {
                    "status": "needs_refinement",
                    "mode": mode,
                    "confidence": confidence,
                    "message": MENSAGEM_PRECISA_REFINAR,
                    "disclaimer": DISCLAIMER_RESPOSTA,
                }

            # 4. Clarification check (apenas CLINICAL_REASONING, sem force, sem answers)
            if mode == "CLINICAL_REASONING" and not force and not clarification_answers:
                clarification = await check_clarification(sanitized_prompt, contexto=history_messages)
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
            # Conversa com material de paciente no contexto NÃO usa cache — nem
            # lê, nem grava. A chave é `(modo, prompt)`, mas a resposta foi
            # gerada com a evolução da pasta junto: servi-la a outro médico
            # entregaria conduta calibrada para um paciente que não é o dele.
            # Ver `contexto_tem_dado_de_paciente`.
            pode_cachear = pode_usar_cache(mode, history_messages)
            if pode_cachear:
                cached, _cache_normalized, _cache_embedding = await get_cached_response(
                    self.db, mode, sanitized_prompt
                )
                if cached is not None:
                    # Os ids devolvidos precisam ser os DESTE usuário: o cache
                    # é global por modo, e os do payload são de quem o populou.
                    # Ver `registrar_hit_de_cache`.
                    conv_id, cached_interaction = await registrar_hit_de_cache(
                        self.db,
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
                    return {
                        **cached,
                        "cache_hit": True,
                        "conversation_id": str(conv_id),
                        "interaction_id": str(cached_interaction.id),
                    }

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
            await link_attachments(self.db, self.user_id, interaction.id, attachment_ids)

            # 5. Roteamento pro agente
            if mode == "PHARMA_CHECK":
                agent_response = await self._handle_pharma_check(sanitized_prompt, interaction.id)
            elif mode in PHARMA_MODE_CONFIG:
                agent_response = await self._handle_pharma(sanitized_prompt, mode)
            else:
                agent_response = await self._handle_ai_agent(mode, sanitized_prompt, image_content=image_content, history=history_messages)

            # 6. Salvar resposta
            cost = Decimal("0")
            if agent_response.get("model_id") and agent_response.get("model_id") != "pharmadb":
                cost = await calculate_cost(
                    self.db,
                    agent_response["model_id"],
                    agent_response.get("tokens_in"),
                    agent_response.get("tokens_out"),
                )
                # Ferramentas integradas (Data Ocean) cobram por GB, busca e
                # minuto de execução — grandezas que `calculate_cost` não vê.
                # Os preços estão em `PRECOS_FERRAMENTAS_BRL` e a conversão usa
                # um câmbio FIXO, que é um gap conhecido: ver `BRL_POR_USD`.
                cost += calcular_custo_ferramentas(agent_response.get("tool_usage"))

            # O custo REAL vai para o trace aqui, e não no provider: quando ele
            # retorna, este número ainda não existe. Sem isto o Phoenix estimava
            # o custo por tokens — o que para o DATA_OCEAN é simplesmente errado,
            # já que o custo dele está em GB e minutos. Ver `set_llm_cost`.
            set_llm_cost(
                get_current_span(),
                cost_usd=cost,
                tool_usage=agent_response.get("tool_usage"),
                mode=mode,
            )

            # DLP na resposta do modelo, NA ORIGEM — antes de gravar e antes de
            # devolver. O texto gravado e o texto devolvido saem de duas leituras
            # separadas deste mesmo dict (aqui e no `return_dict` abaixo):
            # sanitizar só num dos dois faria o médico ver um texto e encontrar
            # outro ao reabrir a conversa. Reescrevendo a chave, os dois usos leem
            # o valor já limpo.
            #
            # `use_ner=False`: ver `sanitize_prompt_async`. Na saída clínica o NER
            # comeria nome de fármaco e de escore, quebrando a retomada da conversa
            # e a extração de medicamentos logo abaixo.
            if agent_response.get("text"):
                agent_response["text"] = (
                    await sanitize_prompt_async(agent_response["text"], use_ner=False)
                ).sanitized_text

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

            # Soma o custo ao medidor semanal do usuário.
            #
            # ISTO FALTAVA. `check_limit` é chamado nos dois endpoints e lê
            # `UserWeeklyUsage.total_cost_usd` — mas só o `/stream` incrementava
            # esse contador. O `/query` era o único produtor de custo do projeto
            # que não registrava: o agregador registra nos dois caminhos, o
            # upload de imagem registra, o stream registra.
            #
            # Efeito: um `beta_user` consumindo pelo `/query` — que é o caminho
            # de TODOS os modos PharmaDB — nunca batia o limite semanal. O custo
            # ficava gravado em `interaction.token_cost_usd` (auditoria) e fora
            # do medidor, e a divergência só apareceria na fatura.
            await record_cost(self.db, self.user_id, cost)

            # 8. Auditoria nasce AQUI, com o que já se sabe — mesmo motivo do
            # `/stream`: um erro no pós-processamento não pode apagar o registro
            # de que a interação existiu. O enriquecimento vem depois, em
            # background.
            audit_base = {
                "mode": mode,
                "triage_confidence": confidence,
                "model_used": agent_response.get("model_id", "pharmadb"),
                "is_fallback": agent_response.get("is_fallback", False),
                "prompt_length": len(prompt),
                "total_cost_usd": str(cost),
                "dlp_sanitized": dlp_result.was_sanitized,
                "dlp_replacements": dlp_result.replacement_count,
                "dlp_by_type": dlp_result.counts_by_type,
            }
            audit = add_interaction_audit(
                self.db,
                user_id=self.user_id,
                interaction_id=interaction.id,
                action="orquestrador_query",
                metadata=audit_base,
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
                # Os sete campos abaixo são apurados pelo pós-processamento, que
                # agora roda em BACKGROUND (ver `_pos_processar_em_background`).
                # Eles saem vazios nesta resposta e são gravados segundos depois.
                #
                # Mantidos no contrato de propósito: o front não os consome aqui
                # (`queryOrquestrador` lê `response_text`, `mode` e
                # `conversation_id`), mas removê-los seria quebra explícita de
                # API — e no `cache_hit` eles voltam preenchidos, que é onde a UI
                # de fato monta o bloco de referências.
                "specialty_detected": None,
                "topic_detected": None,
                "confidence_score": None,
                "low_evidence_alert": False,
                "outdated_alert": False,
                "cited_guidelines_verified": [],
                "newer_guidelines_found": [],
                "total_response_time_ms": elapsed_ms,
                "disclaimer": DISCLAIMER_RESPOSTA,
            }

            # Commit de durabilidade, e ele precisa vir ANTES de agendar a
            # tarefa abaixo — mesmo motivo do `/stream` (ver o commit anterior
            # ao `text_done` lá).
            #
            # A sessão da requisição só seria commitada por `get_db` DEPOIS que
            # este handler retorna. Como `create_task` agenda a corrotina para o
            # próximo ciclo do loop, ela podia começar antes disso e procurar por
            # id, numa sessão nova, registros de uma transação ainda não
            # confirmada — não encontraria nada e sairia em silêncio, deixando a
            # interação para sempre sem especialidade, sem PubMed e fora do
            # cache. Sem erro e sem alerta.
            #
            # O commit de `get_db` continua acontecendo no fim; sem alterações
            # pendentes ele é no-op.
            await self.db.commit()

            # 9. Pós-processamento + gravação no cache, fora do caminho da
            # resposta. Validação PubMed, detecção de especialidade e extração de
            # medicamentos custavam segundos que o médico esperava olhando a
            # tela — o `/stream` já entregava antes disso (`text_done`), e o
            # `/query` é o caminho de TODOS os modos PharmaDB.
            #
            # A gravação no cache vai JUNTO, e não aqui: o `return_dict` ainda
            # não tem as referências do PubMed, e cachear agora serviria resposta
            # sem validação a outro médico — que é justamente o que o `cache_hit`
            # do front lê para montar o bloco "Referências verificadas".
            self._agendar_pos_processamento(
                interaction_id=interaction.id,
                response_id=ir.id,
                audit_id=audit.id,
                audit_base=audit_base,
                sanitized_prompt=sanitized_prompt,
                texto_resposta=agent_response.get("text", ""),
                mode=mode,
                citations=agent_response.get("citations"),
                tool_usage=agent_response.get("tool_usage"),
                cachear=bool(
                    pode_cachear
                    and not agent_response.get("is_fallback")
                    and _cache_embedding
                    and _cache_normalized
                ),
                cache_normalized=_cache_normalized,
                cache_embedding=_cache_embedding,
                payload_base=return_dict,
            )

            return return_dict

        except Exception as e:
            logger.exception("ERRO NO ORQUESTRADOR: %s", e)
            raise

# ── Agente de IA ─────────────────────────────────────────

    async def _handle_ai_agent(self, mode: str, prompt: str, image_content: dict | None = None, history: list[dict] | None = None) -> dict:
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
                model_id, prompt, system_prompt=system_prompt, temperature=temperature, image_content=image_content, history=history
            )
            return {
                "text": response.text,
                "model_id": model_id,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "is_fallback": False,
                # Consumo de ferramentas integradas (Data Ocean). Vai para
                # `extra_metadata` — ver `build_response_metadata`.
                "tool_usage": response.tool_usage,
            }
        except Exception as e:
            # Tipo da exceção junto da mensagem: um `httpx.ReadTimeout` tem
            # `str()` vazio, e o log saía sem dizer que a causa era timeout.
            logger.warning(
                "Falha no %s: %s: %s. Tentando fallback...",
                model_id, type(e).__name__, e or "(sem mensagem)",
            )
            return await self._try_fallback(
                mode, prompt, system_prompt, str(e), history=history, image_content=image_content
            )

    # ── Fallback ─────────────────────────────────────────────

    async def _try_fallback(
        self,
        mode: str,
        prompt: str,
        system_prompt: str,
        original_error: str,
        history: list[dict] | None = None,
        image_content: dict | list | None = None,
    ) -> dict:
        """Tenta a cadeia de fallback do modo.

        `image_content` é repassado: sem isso, uma leitura de exame que caísse
        no fallback perdia a imagem no caminho e o modelo secundário respondia
        sobre um exame que nunca recebeu — com o médico vendo o anexo na tela e
        nenhum aviso de que ele não chegou.
        """
        for fallback_model in FALLBACK_MODELS.get(mode, []):
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
                    "is_fallback": True,
                }
            except Exception as e:
                logger.warning(
                    "Fallback %s também falhou: %s: %s",
                    fallback_model, type(e).__name__, e or "(sem mensagem)",
                )
                continue

        return {
            "text": "Desculpe, não foi possível processar sua consulta no momento. Tente novamente em instantes.",
            "error": original_error,
            "is_fallback": True,
        }

    # ── PHARMA_CHECK ─────────────────────────────────────────

    async def _handle_pharma_check(self, prompt: str, interaction_id) -> dict:
        from app.services.integracoes.pharmadb_service import get_pharmadb_service
        from app.services.medication_extractor import extract_medications

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
        from app.services.integracoes.pharmadb_service import get_pharmadb_service

        pharmadb = get_pharmadb_service()
        buscar_attr, formatar_attr, label = PHARMA_MODE_CONFIG[mode]

        raw, normalized = await self._extrair_nome_medicamento(prompt)
        if not raw and not normalized:
            return {
                "text": "⚠️ Não identifiquei o nome do medicamento na sua pergunta. Por favor, informe o nome do produto.",
                "model_id": "pharmadb",
                "is_fallback": False,
            }

        # O `getattr` fica FORA do `try`: resolver o nome do método é erro de
        # programação (um nome trocado em `PHARMA_MODE_CONFIG`), não falha de
        # infraestrutura. Dentro do `try`, o `AttributeError` caía no `except` e
        # virava "PharmaDB indisponível" — a base no ar, o médico recebendo o
        # aviso de indisponibilidade, e nada no log apontando para a causa real.
        buscar = getattr(pharmadb, buscar_attr)
        try:
            resultado = await self._buscar_com_fallback(buscar, raw, normalized)
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

    def _agendar_pos_processamento(self, **kwargs) -> asyncio.Task | None:
        """
        Dispara o pós-processamento em background e devolve na hora.

        Molde de `folder_context_service.agendar_indexacao`: referência forte
        para o GC não recolher a tarefa no meio, e `done_callback` que drena a
        exceção — sem ele uma falha vira "Task exception was never retrieved"
        solto no log, sem dono.

        Devolve None quando não há event loop (chamada fora de contexto async,
        como em teste síncrono).
        """
        try:
            tarefa = asyncio.create_task(
                _pos_processar_em_background(user_id=self.user_id, **kwargs),
                name=f"pos-processar-{kwargs['interaction_id']}",
            )
        except RuntimeError:  # pragma: no cover — sem loop rodando
            return None

        _pos_em_voo.add(tarefa)

        def _encerrar(t: asyncio.Task) -> None:
            _pos_em_voo.discard(t)
            if not t.cancelled() and t.exception() is not None:
                # A resposta já foi entregue ao médico e a interação já está
                # gravada: o que se perde aqui é metadado (especialidade,
                # PubMed, entrada no cache), não a consulta.
                logger.warning(
                    "[PosProcessamento] Falhou para a interação %s: %s",
                    kwargs["interaction_id"], t.exception(),
                )

        tarefa.add_done_callback(_encerrar)
        return tarefa

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