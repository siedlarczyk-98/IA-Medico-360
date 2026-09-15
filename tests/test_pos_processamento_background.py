"""
O pós-processamento do `/query` roda em BACKGROUND — e termina o serviço.

O QUE MUDOU
Validação PubMed, detecção de especialidade e extração de medicamentos eram
aguardadas antes do `return`: o médico olhava a tela esperando metadado que não
vai ler. O `/stream` já entregava antes disso (`text_done`), e o `/query` é o
caminho de TODOS os modos PharmaDB — era a divergência `/query`↔`/stream`
aparecendo de novo, desta vez em latência.

POR QUE ESTE ARQUIVO EXISTE
Mover trabalho para `create_task` cria duas classes de defeito SILENCIOSO, e
nenhuma delas aparece num teste que só confere o retorno da rota:

1. A tarefa nunca roda, ou roda e falha — e a resposta continua 200. A interação
   fica para sempre sem especialidade, sem PubMed e fora do cache.
2. A tarefa roda ANTES do commit da requisição. Como ela abre sessão própria,
   procura por id registros de uma transação ainda não confirmada, não encontra
   nada e sai em silêncio. Foi o defeito real encontrado ao escrever o T8: o
   commit do `/query` só acontecia em `get_db`, DEPOIS do handler retornar.

Por isso os testes abaixo AGUARDAM a tarefa e verificam o efeito no banco.
"""

import asyncio
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import Interaction, InteractionMedication
from app.services import orquestrador_service, orquestrador_shared
from app.services.integracoes.ai_providers import ProviderResponse

pytestmark = pytest.mark.asyncio


def _sessao_do_teste(monkeypatch, db_conn):
    """
    Faz a tarefa de background usar a conexão DO TESTE.

    A tarefa abre sessão própria via `async_session_factory` — correto em
    produção, mas dentro do harness ela não enxergaria nada: o fixture prende
    tudo numa transação revertida no fim. Montar a factory sobre `db_conn` é o
    padrão que `test_folder_context` e `test_orquestrador_stream` já usam para
    testar justamente esse tipo de código.
    """
    monkeypatch.setattr(
        orquestrador_service, "async_session_factory",
        async_sessionmaker(bind=db_conn, expire_on_commit=False),
    )


class _PubmedFalso:
    confidence_score = 0.9
    low_evidence_alert = False
    outdated_alert = False
    fallback = False
    cited_guidelines_verified = ()
    newer_guidelines_found = ()


def _falsifica_pos_processamento(monkeypatch, *, especialidade="Cardiologia"):
    """Substitui as três chamadas externas do pós-processamento."""

    async def especialidade_falsa(_prompt):
        return {"specialty": especialidade, "topic": "fibrilação atrial"}

    async def medicamentos_falsos(_prompt, _respostas):
        return [{
            "medication_raw": "varfarina",
            "medication_normalized": "varfarina",
            "source": "teste",
        }]

    async def pubmed_falso(**_kwargs):
        return _PubmedFalso()

    monkeypatch.setattr(orquestrador_shared, "detect_specialty_and_topic", especialidade_falsa)
    monkeypatch.setattr(orquestrador_shared, "extract_from_interaction", medicamentos_falsos)
    monkeypatch.setattr(orquestrador_shared, "validate_with_pubmed", pubmed_falso)


def _falsifica_provider(monkeypatch, texto="Anticoagulação plena indicada."):
    """Provider que responde sem rede.

    Devolve `ProviderResponse`, e não dict: o serviço lê `.text`, e um dict
    aqui faz a chamada cair no fallback silenciosamente.
    """

    class ProviderFalso:
        async def complete(self, *_a, **_kw):
            return ProviderResponse(
                text=texto,
                tokens_in=100,
                tokens_out=50,
                model_id="claude-sonnet-4-6",
                provider="anthropic",
            )

    monkeypatch.setattr(
        orquestrador_service, "get_provider_by_type", lambda *_a, **_kw: ProviderFalso()
    )


async def _aguardar_pos_processamento():
    """
    Espera as tarefas de pós-processamento em voo.

    Sem isto o teste passaria mesmo que a tarefa nunca rodasse — que é
    exatamente o modo de falha que este arquivo existe para pegar.
    """
    for _ in range(50):
        em_voo = [t for t in orquestrador_service._pos_em_voo if not t.done()]
        if not em_voo:
            break
        await asyncio.gather(*em_voo, return_exceptions=True)
    await asyncio.sleep(0)


# ── A tarefa é de fato agendada ──────────────────────────────────────────


async def test_saudacao_nao_agenda_pos_processamento(db, user):
    """
    Atalho de saudação não chama modelo nem apura metadado — agendar tarefa aqui
    seria trabalho puro para responder "bom dia".
    """
    antes = len(orquestrador_service._pos_em_voo)

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="bom dia")

    assert resposta["mode"] == "OFF_TOPIC"
    assert len(orquestrador_service._pos_em_voo) == antes


# ── O contrato da resposta ───────────────────────────────────────────────


async def test_resposta_sai_com_os_campos_de_metadado_vazios(
    db, db_conn, user, monkeypatch, model_pricing_factory
):
    """
    Os sete campos apurados pelo pós-processamento continuam no contrato, mas
    saem vazios: o front (`queryOrquestrador`) lê só `response_text`, `mode` e
    `conversation_id`, e removê-los seria quebra explícita de API.

    Se algum dia voltarem preenchidos, é porque o pós-processamento voltou a ser
    aguardado — e a latência voltou junto.
    """
    await model_pricing_factory(
        model_id="claude-sonnet-4-6", provider_type="anthropic",
        input_per_million="3.00", output_per_million="15.00",
    )
    _sessao_do_teste(monkeypatch, db_conn)
    _falsifica_provider(monkeypatch)
    _falsifica_pos_processamento(monkeypatch)

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="conduta para FA com CHA2DS2-VASc 4", mode="CLINICAL_REASONING")

    await _aguardar_pos_processamento()

    assert resposta["response_text"]
    assert resposta["specialty_detected"] is None
    assert resposta["topic_detected"] is None
    assert resposta["confidence_score"] is None
    assert resposta["low_evidence_alert"] is False
    assert resposta["outdated_alert"] is False
    assert resposta["cited_guidelines_verified"] == []
    assert resposta["newer_guidelines_found"] == []


# ── O efeito acontece, ainda que depois ──────────────────────────────────


async def test_especialidade_e_gravada_pelo_background(
    db, db_conn, user, monkeypatch, model_pricing_factory
):
    """
    O teste que pega a corrida: a tarefa abre sessão PRÓPRIA e busca por id. Se
    a requisição não tiver commitado antes de agendar, ela não encontra nada e
    sai em silêncio — a interação fica sem especialidade para sempre.
    """
    await model_pricing_factory(
        model_id="claude-sonnet-4-6", provider_type="anthropic",
        input_per_million="3.00", output_per_million="15.00",
    )
    _sessao_do_teste(monkeypatch, db_conn)
    _falsifica_provider(monkeypatch)
    _falsifica_pos_processamento(monkeypatch, especialidade="Cardiologia")

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(
        prompt="conduta para FA com CHA2DS2-VASc 4", mode="CLINICAL_REASONING"
    )

    await _aguardar_pos_processamento()

    interacao = await db.get(Interaction, UUID(resposta["interaction_id"]))
    await db.refresh(interacao)

    assert interacao.specialty_detected == "Cardiologia", (
        "O pós-processamento em background não gravou a especialidade — "
        "provavelmente a tarefa rodou antes do commit da requisição."
    )
    assert interacao.topic_detected == "fibrilação atrial"


async def test_medicamentos_sao_extraidos_pelo_background(
    db, db_conn, user, monkeypatch, model_pricing_factory
):
    """Mesma verificação, num efeito que cria linha nova em vez de atualizar."""
    await model_pricing_factory(
        model_id="claude-sonnet-4-6", provider_type="anthropic",
        input_per_million="3.00", output_per_million="15.00",
    )
    _sessao_do_teste(monkeypatch, db_conn)
    _falsifica_provider(monkeypatch)
    _falsifica_pos_processamento(monkeypatch)

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(
        prompt="anticoagular?", mode="CLINICAL_REASONING"
    )

    await _aguardar_pos_processamento()

    meds = (await db.execute(
        select(InteractionMedication).where(
            InteractionMedication.interaction_id == UUID(resposta["interaction_id"])
        )
    )).scalars().all()

    assert [m.medication_normalized for m in meds] == ["varfarina"]


# ── A falha é contida ────────────────────────────────────────────────────


async def test_falha_no_background_nao_derruba_a_resposta(
    db, db_conn, user, monkeypatch, model_pricing_factory, caplog
):
    """
    A resposta já foi entregue e a interação já está gravada: o que se perde
    numa falha aqui é metadado, não a consulta. E não pode virar
    "Task exception was never retrieved" solto no log — por isso o
    `done_callback` drena a exceção.
    """
    await model_pricing_factory(
        model_id="claude-sonnet-4-6", provider_type="anthropic",
        input_per_million="3.00", output_per_million="15.00",
    )
    _sessao_do_teste(monkeypatch, db_conn)
    _falsifica_provider(monkeypatch)

    async def pubmed_explode(**_kwargs):
        raise RuntimeError("E-utilities fora do ar")

    async def especialidade_falsa(_p):
        return {"specialty": "Clínica Médica", "topic": "geral"}

    async def medicamentos_falsos(_p, _r):
        return []

    monkeypatch.setattr(orquestrador_shared, "detect_specialty_and_topic", especialidade_falsa)
    monkeypatch.setattr(orquestrador_shared, "extract_from_interaction", medicamentos_falsos)
    monkeypatch.setattr(orquestrador_shared, "validate_with_pubmed", pubmed_explode)

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="dose de AAS?", mode="CLINICAL_REASONING")

    # A resposta ao médico não é afetada.
    assert resposta["status"] == "ok"
    assert resposta["response_text"]

    await _aguardar_pos_processamento()

    # E a falha foi registrada, não engolida.
    assert any(
        "PosProcessamento" in r.message or "PosProcessamento" in str(r.msg)
        for r in caplog.records
    ), "A falha do background precisa aparecer no log"
