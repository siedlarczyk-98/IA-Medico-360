"""
Paridade entre `/orquestrador/query` e `/orquestrador/stream`.

Os dois serviços nasceram como cópias um do outro e ja tinham divergido — a mais
cara sendo o atalho de saudacao, que existia so no streaming. No `/query`, a
triagem devolvendo OFF_TOPIC levava a `MODE_MODEL_MAP["OFF_TOPIC"]`, que
estourava KeyError: o médico dizia "bom dia" e recebia erro interno.

Estes testes travam o que agora é compartilhado. Se voltarem a divergir, falham
aqui e não em produção.
"""

import pytest

from app.services import orquestrador_service, orquestrador_stream_service
from app.services.orquestrador_modes import (
    MODE_MODEL_MAP,
    VALID_MODES,
    OrquestradorMode,
)
from app.services.orquestrador_shared import make_title

# ── Modos ────────────────────────────────────────────────────────────────────

def test_todo_modo_valido_tem_roteamento_declarado():
    """Um modo sem entrada no mapa e um KeyError esperando o usuario certo."""
    faltando = VALID_MODES - MODE_MODEL_MAP.keys()
    assert not faltando, f"Modos sem entrada em MODE_MODEL_MAP: {faltando}"


def test_off_topic_nao_roteia_para_modelo():
    # OFF_TOPIC e atendido por atalho local; ter um modelo aqui significaria
    # gastar chamada de LLM para responder "bom dia".
    assert MODE_MODEL_MAP[OrquestradorMode.OFF_TOPIC] is None


def test_modos_pharma_nao_roteiam_para_modelo():
    for modo in ("PHARMA_CHECK", "PHARMA_BULA", "PHARMA_RECEITA", "PHARMA_GENERICO"):
        assert MODE_MODEL_MAP[modo] is None


def test_os_dois_servicos_usam_o_mesmo_mapa_de_modelo():
    """Antes eram dois dicionarios literais, e ja diferiam entre si."""
    assert orquestrador_service.MODE_MODEL_MAP is orquestrador_stream_service.MODE_MODEL_MAP


def test_os_dois_servicos_usam_a_mesma_temperatura():
    assert (
        orquestrador_service.MODE_TEMPERATURE_MAP
        is orquestrador_stream_service.MODE_TEMPERATURE_MAP
    )


def test_enum_e_a_lista_de_modos_validos_nao_divergem():
    assert VALID_MODES == {m.value for m in OrquestradorMode}


# A montagem de contexto (antes `build_enriched_prompt`, hoje turnos com
# orçamento de tokens) tem casa própria em tests/test_contexto.py.


# ── Titulo ───────────────────────────────────────────────────────────────────

def test_titulo_ignora_prefixo_de_imagem():
    # Sem isto a conversa se chamaria "[Imagem: exame.png]".
    assert make_title("[Imagem: exame.png]\n\nlaudo de tomografia") == "laudo de tomografia"


def test_titulo_ignora_texto_de_arquivo_anexado():
    assert make_title("[Arquivo: a.pdf]\nconteudo\n\n---\n\npergunta real") == "pergunta real"


def test_titulo_longo_e_truncado_com_reticencias():
    titulo = make_title("a" * 200)
    assert len(titulo) == 103
    assert titulo.endswith("...")


# ── Saudacao ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_saudacao_no_query_nao_estoura_keyerror(db, user):
    """A regressao: antes disto, "bom dia" no /query virava erro interno."""
    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="bom dia")

    assert resposta["status"] == "ok"
    assert resposta["mode"] == "OFF_TOPIC"
    assert resposta["model_used"] == "off_topic_shortcut"
    assert resposta["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_saudacao_no_query_nao_gasta_chamada_de_modelo(db, user, monkeypatch):
    """Responder "oi" com um LLM e custo puro."""
    def explode(*args, **kwargs):
        raise AssertionError("nenhum provider deveria ser chamado numa saudacao")

    monkeypatch.setattr(orquestrador_service, "get_provider_by_type", explode)
    monkeypatch.setattr(orquestrador_service, "triage", explode)

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="olá")

    assert resposta["mode"] == "OFF_TOPIC"


@pytest.mark.asyncio
async def test_saudacao_responde_o_mesmo_texto_nos_dois_caminhos(db, user):
    """O médico nao deve receber respostas diferentes por causa do transporte."""
    from app.services.orquestrador_modes import GREETING_REPLY

    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="bom dia")

    assert resposta["response_text"] == GREETING_REPLY


@pytest.mark.asyncio
async def test_saudacao_entra_no_historico(db, user):
    servico = orquestrador_service.OrquestradorService(db=db, user_id=user.id)
    resposta = await servico.query(prompt="oi")

    assert resposta["conversation_id"]
    assert resposta["interaction_id"]
