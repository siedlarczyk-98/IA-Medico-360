"""
Modo DATA_OCEAN: bases de dados públicas brasileiras via Maritaca.

O Data Ocean é uma ferramenta AGÊNTICA que roda do lado da Maritaca — o Sabiá
decide quais bases consultar, executa as consultas e devolve só a resposta
final. Isso traz três restrições que não existem nos outros modos, e é o que
este arquivo protege:

1. **Sem fallback.** Nenhum outro modelo consulta as bases brasileiras. Cair
   para o Claude devolveria uma resposta fluente construída da MEMÓRIA, com
   números possivelmente inventados, com a mesma aparência de uma consulta real
   ao DATASUS. Falhar visivelmente é melhor do que isso.
2. **Sem cache.** Alerta epidemiológico, leito livre e cobertura vacinal mudam
   por dia. Servir do cache entregaria número velho com cara de atual.
3. **Sem triagem.** O modo é lento e cobrado por uso de ferramenta; só o médico
   o aciona.
"""

from decimal import Decimal

import pytest

from app.core.prompts import MODE_SYSTEM_PROMPTS
from app.services import orquestrador_shared
from app.services.integracoes.ai_providers import (
    PROVIDER_TYPE_REGISTRY,
    MaritacaProvider,
    ProviderResponse,
)
from app.services.orquestrador_modes import (
    FALLBACK_MODELS,
    MODE_MODEL_MAP,
    MODOS_CACHEAVEIS,
    MODOS_NAO_TRIADOS,
    VALID_MODES,
    OrquestradorMode,
)

# ── Registro do modo ─────────────────────────────────────────────────────────

def test_modo_esta_registrado_em_todos_os_mapas():
    """`orquestrador_modes` existe porque esquecer um mapa falhava em runtime,
    não no import. Este teste é o guarda dessa promessa para o modo novo."""
    assert OrquestradorMode.DATA_OCEAN in VALID_MODES
    assert MODE_MODEL_MAP[OrquestradorMode.DATA_OCEAN] == "sabia-4-thinking"
    assert "DATA_OCEAN" in MODE_SYSTEM_PROMPTS


def test_o_modelo_do_modo_suporta_a_ferramenta():
    """A API devolve 400 se `data_ocean` for pedido num modelo incompatível.

    Trocar o modelo do modo por um `sabia-3`, por exemplo, quebraria o recurso
    inteiro — e só em produção, na primeira pergunta.
    """
    modelo = MODE_MODEL_MAP[OrquestradorMode.DATA_OCEAN]
    assert modelo in MaritacaProvider.MODELOS_COM_FERRAMENTAS


def test_provider_maritaca_esta_no_registry():
    assert "maritaca" in PROVIDER_TYPE_REGISTRY


# ── As três restrições ───────────────────────────────────────────────────────

def test_nao_tem_fallback_para_modelo_sem_as_bases():
    """A ausência de fallback É a decisão, não um esquecimento.

    Um modelo comum responderia com fluência e sem dado nenhum, e o médico não
    teria como distinguir isso de uma consulta real.
    """
    assert not FALLBACK_MODELS.get(OrquestradorMode.DATA_OCEAN)


def test_nao_e_cacheavel():
    """Alerta de dengue e leito livre mudam por dia."""
    assert OrquestradorMode.DATA_OCEAN not in MODOS_CACHEAVEIS


@pytest.mark.asyncio
async def test_triagem_nunca_escolhe_o_modo(monkeypatch):
    """Mesmo que o modelo de triagem devolva DATA_OCEAN, ele é descartado.

    O prompt de triagem nem lista o modo, mas um LLM pode devolver qualquer
    string — e um DATA_OCEAN vindo daí mandaria uma pergunta clínica comum para
    um caminho lento e cobrado, sem ninguém ter pedido.
    """
    async def _triagem(_):
        return {"mode": "DATA_OCEAN", "confidence": 0.99}

    monkeypatch.setattr(orquestrador_shared, "triage", _triagem)
    decisao = await orquestrador_shared.decidir_rota("quantos leitos em Campinas?", None, False)

    assert decisao.mode != "DATA_OCEAN"
    assert OrquestradorMode.DATA_OCEAN in MODOS_NAO_TRIADOS


@pytest.mark.asyncio
async def test_modo_explicito_do_medico_e_respeitado():
    """A contrapartida: quando o médico ESCOLHE, o modo vale e não passa por
    triagem nenhuma."""
    decisao = await orquestrador_shared.decidir_rota("dengue em Campinas", "DATA_OCEAN", False)

    assert decisao.mode == "DATA_OCEAN"
    assert decisao.confidence == 1.0


# ── Contrato com a API da Maritaca ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_liga_a_flag_e_desliga_o_streaming(monkeypatch):
    """Os dois lados do contrato documentado: a flag `data_ocean` no corpo, e
    `stream: false` — com ferramenta ligada, streaming devolve 400."""
    capturado = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {
                "choices": [{"message": {"content": "Campinas tem 1.139.047 habitantes."}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 139},
            }

    class _Client:
        async def post(self, url, **kwargs):
            capturado["url"] = url
            capturado["json"] = kwargs.get("json")
            capturado["timeout"] = kwargs.get("timeout")
            return _Resp()

    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: _Client())

    await MaritacaProvider().complete("sabia-4-thinking", "Quantos habitantes tem Campinas?")

    assert capturado["json"]["data_ocean"] is True
    assert capturado["json"]["stream"] is False
    assert capturado["url"] == MaritacaProvider.BASE_URL


@pytest.mark.asyncio
async def test_modelo_incompativel_falha_antes_de_gastar_a_chamada(monkeypatch):
    """A API devolveria 400; falhar aqui diz o que houve, em vez de um erro
    HTTP opaco no meio de uma consulta."""
    def _nao_deveria_chamar():
        raise AssertionError("não deveria ter feito requisição")

    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", _nao_deveria_chamar)

    with pytest.raises(ValueError, match="não aceita a ferramenta Data Ocean"):
        await MaritacaProvider().complete("sabia-3", "pergunta")


@pytest.mark.asyncio
async def test_uso_de_ferramentas_volta_na_resposta(monkeypatch):
    """`tool_execution_details` é o que permite gravar o custo real — sem ele,
    o modo mais caro da plataforma parece o mais barato nos relatórios."""
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 139,
                    "tool_execution_details": {
                        "web_search_calls": 2,
                        "page_reads": 5,
                        "data_ocean_gb_processed": 0.000161,
                        "code_execution_minutes": 1,
                    },
                },
            }

    class _Client:
        async def post(self, url, **kwargs):
            return _Resp()

    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: _Client())

    resp = await MaritacaProvider().complete("sabia-4-thinking", "dengue em Campinas")

    assert resp.tool_usage == {
        "web_search_calls": 2,
        "page_reads": 5,
        "data_ocean_gb_processed": 0.000161,
        "code_execution_minutes": 1,
    }


@pytest.mark.asyncio
async def test_resposta_sem_ferramenta_executada_nao_quebra(monkeypatch):
    """`tool_execution_details` só aparece quando alguma ferramenta rodou.

    Quem grava custo não deveria precisar saber disso — as chaves vêm zeradas.
    """
    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            }

    class _Client:
        async def post(self, url, **kwargs):
            return _Resp()

    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: _Client())

    resp = await MaritacaProvider().complete("sabia-4-thinking", "oi")

    assert resp.tool_usage["data_ocean_gb_processed"] == 0.0


@pytest.mark.asyncio
async def test_stream_e_simulado_e_preserva_o_uso_de_ferramentas(monkeypatch):
    """A API não aceita streaming com ferramenta. O texto é fatiado a partir de
    `complete()`, e o token final precisa carregar o uso — senão o custo se
    perde justamente no caminho que o médico usa."""
    async def _complete(self, model_id, prompt, **kwargs):
        return ProviderResponse(
            text="resposta com dados do DATASUS",
            tokens_in=10,
            tokens_out=20,
            tool_usage={"data_ocean_gb_processed": 0.5},
        )

    monkeypatch.setattr(MaritacaProvider, "complete", _complete)

    tokens = [t async for t in MaritacaProvider().stream("sabia-4-thinking", "pergunta")]

    texto = "".join(t.delta for t in tokens)
    assert texto == "resposta com dados do DATASUS"
    assert tokens[-1].done is True
    assert tokens[-1].tool_usage == {"data_ocean_gb_processed": 0.5}


# ── Persistência do consumo ──────────────────────────────────────────────────
# O custo do Data Ocean não é o custo por token: `data_ocean: true` liga junto
# busca na web e execução de código, e as três são cobradas por USO. Sem
# guardar `tool_execution_details`, o modo mais caro da plataforma apareceria
# nos relatórios com o custo de uma completion comum.

def test_uso_de_ferramentas_e_guardado_na_resposta():
    from app.services.response_metadata import build_response_metadata

    meta = build_response_metadata(
        tool_usage={"data_ocean_gb_processed": 0.5, "web_search_calls": 2},
    )

    assert meta["tool_usage"]["data_ocean_gb_processed"] == 0.5


def test_uso_e_guardado_cru_e_nao_convertido_em_dolar():
    """A tabela de preços dessas ferramentas ainda não está no projeto.

    Guardar o dado bruto desde o primeiro dia permite converter depois,
    retroativamente. Um custo calculado com preço chutado é pior: parece certo.
    """
    from app.services.response_metadata import build_response_metadata

    meta = build_response_metadata(tool_usage={"data_ocean_gb_processed": 0.5})

    assert "cost" not in str(meta["tool_usage"]).lower()
    assert meta["tool_usage"] == {"data_ocean_gb_processed": 0.5}


def test_resposta_sem_ferramenta_nao_polui_o_metadata():
    """A maioria das respostas não usa ferramenta nenhuma."""
    from app.services.response_metadata import build_response_metadata

    assert build_response_metadata(tool_usage=None) is None
    assert build_response_metadata(tool_usage={}) is None


# ── Custo das ferramentas ────────────────────────────────────────────────────
# Os preços da Maritaca são em REAIS; todo o resto do sistema calcula em USD.
# A conversão usa um câmbio FIXO (`BRL_POR_USD`), que é um gap conhecido e
# aceito — documentado na constante. Estes testes travam a aritmética e o
# vínculo com a tabela publicada.

def test_precos_batem_com_a_tabela_publicada_da_maritaca():
    """Trava os valores contra a página de preços.

    Se a Maritaca reajustar, o teste falha e obriga a olhar a fonte — em vez de
    o custo divergir da fatura em silêncio por meses.
    """
    from app.services.pricing import PRECOS_FERRAMENTAS_BRL

    assert PRECOS_FERRAMENTAS_BRL["data_ocean_gb_processed"] == Decimal("0.10")
    assert PRECOS_FERRAMENTAS_BRL["web_search_calls"] == Decimal("0.0165")
    assert PRECOS_FERRAMENTAS_BRL["page_reads"] == Decimal("0.066")
    assert PRECOS_FERRAMENTAS_BRL["code_execution_minutes"] == Decimal("0.016")


def test_custo_e_convertido_de_real_para_dolar():
    """O resto do sistema grava `cost_usd`; a Maritaca cobra em real."""
    from app.services.pricing import BRL_POR_USD, calcular_custo_ferramentas

    # 1 GB processado = R$ 0,10
    custo = calcular_custo_ferramentas({"data_ocean_gb_processed": 1})

    assert custo == (Decimal("0.10") / BRL_POR_USD).quantize(Decimal("0.000001"))


def test_soma_todas_as_unidades_cobradas():
    """`data_ocean: true` liga busca e execução de código junto — as três são
    cobradas na mesma requisição."""
    from app.services.pricing import BRL_POR_USD, calcular_custo_ferramentas

    custo = calcular_custo_ferramentas({
        "data_ocean_gb_processed": 0.5,     # R$ 0,05
        "web_search_calls": 2,              # R$ 0,033
        "page_reads": 5,                    # R$ 0,33
        "code_execution_minutes": 1,        # R$ 0,016
    })

    esperado_brl = Decimal("0.05") + Decimal("0.033") + Decimal("0.33") + Decimal("0.016")
    assert custo == (esperado_brl / BRL_POR_USD).quantize(Decimal("0.000001"))


def test_sem_consumo_nao_cobra():
    """A maioria das respostas não usa ferramenta nenhuma."""
    from app.services.pricing import calcular_custo_ferramentas

    assert calcular_custo_ferramentas(None) == Decimal("0")
    assert calcular_custo_ferramentas({}) == Decimal("0")


def test_unidade_desconhecida_nao_derruba_o_calculo():
    """Se a Maritaca reportar uma unidade nova, o custo das demais ainda vale —
    e `custo_de_ferramentas_e_conhecido` é quem sinaliza a lacuna."""
    from app.services.pricing import BRL_POR_USD, calcular_custo_ferramentas

    custo = calcular_custo_ferramentas({
        "data_ocean_gb_processed": 1,
        "unidade_que_ainda_nao_existe": 999,
    })

    assert custo == (Decimal("0.10") / BRL_POR_USD).quantize(Decimal("0.000001"))


def test_o_cambio_fixo_esta_documentado_como_gap():
    """O câmbio é fixo e o dólar flutua: todo custo deste provider carrega esse
    erro. A decisão foi aceitar e documentar — este teste garante que a
    explicação não seja apagada num refactor, deixando um número mágico."""
    import inspect

    from app.services import pricing

    fonte = inspect.getsource(pricing)
    i = fonte.find("BRL_POR_USD = ")
    contexto = fonte[max(0, i - 1400):i]

    assert "GAP CONHECIDO" in contexto, "a natureza aproximada do câmbio saiu do código"
    assert "flutua" in contexto
