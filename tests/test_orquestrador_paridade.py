"""
Paridade entre `/orquestrador/query` e `/orquestrador/stream`.

Os dois serviços nasceram como cópias um do outro e ja tinham divergido — a mais
cara sendo o atalho de saudacao, que existia so no streaming. No `/query`, a
triagem devolvendo OFF_TOPIC levava a `MODE_MODEL_MAP["OFF_TOPIC"]`, que
estourava KeyError: o médico dizia "bom dia" e recebia erro interno.

Estes testes travam o que agora é compartilhado. Se voltarem a divergir, falham
aqui e não em produção.
"""

import pathlib

import pytest

from app.services import orquestrador_service, orquestrador_shared, orquestrador_stream_service
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
    # A triagem vive em `orquestrador_shared` desde que os dois caminhos
    # passaram a compartilhar o roteamento.
    monkeypatch.setattr(orquestrador_shared, "triage", explode)

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


# ── Roteamento ───────────────────────────────────────────────────────────────
# O bloco de triagem/roteamento era o mesmo código escrito duas vezes, com os
# limiares (0.7 e PHARMA_CHECK_MIN_CONFIDENCE) como literais em cada arquivo.
# JÁ TINHA DIVERGIDO: na mesma situação de confiança baixa, o `/query` dizia
# "Preciso de um pouco mais de aprofundamento PARA TE INDICAR O AGENTE CORRETO"
# e o `/stream` dizia só "Preciso de um pouco mais de aprofundamento" — mesma
# pergunta, resposta diferente conforme o transporte.


@pytest.mark.asyncio
async def test_modo_explicito_dispensa_triagem():
    """Se o frontend já escolheu o agente, gastar uma chamada de LLM é desperdício."""
    decisao = await orquestrador_shared.decidir_rota("qualquer coisa", "QUICK_SEARCH", False)
    assert decisao.mode == "QUICK_SEARCH"
    assert decisao.confidence == 1.0
    assert decisao.precisa_refinar is False


@pytest.mark.asyncio
async def test_confianca_baixa_pede_reformulacao(monkeypatch):
    async def _triagem(_):
        return {"mode": "CLINICAL_REASONING", "confidence": 0.4}

    monkeypatch.setattr(orquestrador_shared, "triage", _triagem)
    decisao = await orquestrador_shared.decidir_rota("hmm", None, False)

    assert decisao.precisa_refinar is True


@pytest.mark.asyncio
async def test_pharma_check_explicito_ignora_o_gate_de_confianca(monkeypatch):
    """O usuário já escolheu o modo — a triagem serve só para achar o sub-modo."""
    async def _triagem(_):
        return {"mode": "PHARMA_BULA", "confidence": 0.3}

    monkeypatch.setattr(orquestrador_shared, "triage", _triagem)
    decisao = await orquestrador_shared.decidir_rota("bula de losartana", "PHARMA_CHECK", False)

    assert decisao.precisa_refinar is False


@pytest.mark.asyncio
async def test_submodo_pharma_inseguro_cai_para_busca_rapida(monkeypatch):
    """Responder a bula errada é pior do que responder de forma genérica."""
    async def _triagem(_):
        return {"mode": "PHARMA_BULA", "confidence": 0.8}

    monkeypatch.setattr(orquestrador_shared, "triage", _triagem)
    decisao = await orquestrador_shared.decidir_rota("algo sobre remédio", None, False)

    assert decisao.mode == "QUICK_SEARCH"


@pytest.mark.asyncio
async def test_anexo_promove_raciocinio_clinico_para_leitura_de_exame():
    """A triagem só vê o TEXTO e não sabe que veio anexo.

    "O que você acha disso?" com uma tomografia junto e a mesma frase sem anexo
    pedem modos diferentes — a promoção acontece aqui, não lá.
    """
    decisao = await orquestrador_shared.decidir_rota("o que você acha", "CLINICAL_REASONING", True)
    assert decisao.mode == "EXAM_REVIEW"


@pytest.mark.asyncio
async def test_anexo_nao_promove_produtividade():
    """Anexar um documento e pedir "resuma isto" continua sendo produtividade."""
    decisao = await orquestrador_shared.decidir_rota("resuma isto", "PRODUCTIVITY", True)
    assert decisao.mode == "PRODUCTIVITY"


def test_os_dois_servicos_pedem_reformulacao_com_o_mesmo_texto():
    """A divergência que este bloco veio consertar.

    Um texto por transporte significa que o médico recebe respostas diferentes
    para a mesma pergunta, dependendo de o frontend ter pedido streaming.
    """
    assert (
        orquestrador_service.MENSAGEM_PRECISA_REFINAR
        is orquestrador_stream_service.MENSAGEM_PRECISA_REFINAR
    )


def test_o_limiar_de_confianca_existe_num_lugar_so():
    """Estava como literal `0.7` nos dois arquivos."""
    from app.services.orquestrador_shared import CONFIANCA_MINIMA_TRIAGEM

    assert 0 < CONFIANCA_MINIMA_TRIAGEM < 1
    for fonte in ("orquestrador_service", "orquestrador_stream_service"):
        caminho = pathlib.Path("app/services") / f"{fonte}.py"
        assert "0.7" not in caminho.read_text(encoding="utf-8"), (
            f"{fonte} voltou a ter o limiar escrito à mão"
        )
