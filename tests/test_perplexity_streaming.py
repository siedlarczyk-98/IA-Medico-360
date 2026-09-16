"""
QUICK_SEARCH streama de verdade.

O PROBLEMA
`PerplexityProvider.stream` chamava `complete()` e fatiava o texto em pedaços de
20 caracteres. O médico não via nada até a Perplexity terminar de buscar e gerar
— tipicamente 3 a 15 segundos de tela parada — e então o texto aparecia todo de
uma vez, "digitado" a 20 caracteres por 15ms.

QUICK_SEARCH é o modo mais usado da plataforma (107 de 240 interações medidas em
produção) e o que se chama "busca rápida".

A JUSTIFICATIVA QUE CAIU
O comentário dizia: "Perplexity não retorna usage no modo streaming — usamos
complete() para garantir contagem de tokens e custo corretos". A API é
compatível com a da OpenAI e aceita `stream_options: {"include_usage": True}`,
que faz o `usage` chegar no último evento — o mesmo mecanismo que
`OpenAIProvider.stream` já usava neste projeto.
"""

import inspect

import pytest

from app.services.integracoes.ai_providers import PerplexityProvider

pytestmark = pytest.mark.asyncio


class _RespostaSSE:
    """Simula a resposta em streaming da API."""

    def __init__(self, linhas):
        self._linhas = linhas

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for linha in self._linhas:
            yield linha


class _ClienteFake:
    def __init__(self, linhas):
        self._linhas = linhas
        self.corpo = None

    def stream(self, metodo, url, **kwargs):
        self.corpo = kwargs.get("json")
        linhas = self._linhas

        class _Ctx:
            async def __aenter__(self):
                return _RespostaSSE(linhas)

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def _evento(texto=None, usage=None, citations=None, search_results=None) -> str:
    import json
    corpo = {}
    if texto is not None:
        corpo["choices"] = [{"delta": {"content": texto}}]
    if usage is not None:
        corpo["usage"] = usage
    if citations is not None:
        corpo["citations"] = citations
    # `search_results` é a forma moderna, com título; `citations` é o legado só
    # com URLs. A API manda as duas, e os testes cobrem cada uma isolada.
    if search_results is not None:
        corpo["search_results"] = search_results
    return "data: " + json.dumps(corpo)


async def test_o_texto_sai_em_pedacos_conforme_chega(monkeypatch):
    """O ponto do exercício: o médico vê a resposta se formando."""
    cliente = _ClienteFake([
        _evento("Os betabloqueadores "),
        _evento("de primeira linha "),
        _evento("são..."),
        _evento(usage={"prompt_tokens": 100, "completion_tokens": 50}),
        "data: [DONE]",
    ])
    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: cliente)

    tokens = [t async for t in PerplexityProvider().stream("sonar-pro", "pergunta")]

    deltas = [t.delta for t in tokens if t.delta]
    assert deltas == ["Os betabloqueadores ", "de primeira linha ", "são..."], (
        "o texto não está saindo conforme chega da API"
    )


async def test_pede_o_usage_no_streaming(monkeypatch):
    """`stream_options` é o que faz a contagem de tokens chegar — sem ele, a
    justificativa antiga (usar complete()) voltaria a valer."""
    cliente = _ClienteFake(["data: [DONE]"])
    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: cliente)

    [t async for t in PerplexityProvider().stream("sonar-pro", "pergunta")]

    assert cliente.corpo["stream"] is True
    assert cliente.corpo["stream_options"] == {"include_usage": True}


async def test_tokens_e_citacoes_voltam_no_token_final(monkeypatch):
    """O custo e as fontes precisam sobreviver ao streaming — era exatamente o
    que a versão antiga protegia ao não streamar."""
    cliente = _ClienteFake([
        _evento("texto", citations=["https://fonte.example"]),
        _evento(usage={"prompt_tokens": 120, "completion_tokens": 45}),
        "data: [DONE]",
    ])
    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: cliente)

    tokens = [t async for t in PerplexityProvider().stream("sonar-pro", "pergunta")]

    final = tokens[-1]
    assert final.done is True
    assert final.tokens_in == 120
    assert final.tokens_out == 45
    # `Citacao`, não a URL crua: o provider passou a carregar o título quando a
    # API o manda. Aqui o evento só tem o campo legado `citations`, então o
    # título vem `None` — e é assim que fica para sempre nesse caminho.
    assert [(c.url, c.titulo) for c in final.citations] == [
        ("https://fonte.example", None)
    ]


async def test_usage_ausente_vira_aviso_e_nao_silencio(monkeypatch, caplog):
    """Se a API parar de mandar `usage`, o custo vai a zero.

    Isso é aceitável (a resposta já chegou ao médico) desde que apareça: um
    buraco silencioso na contabilidade era o risco que a versão antiga evitava.
    """
    cliente = _ClienteFake([_evento("texto sem usage"), "data: [DONE]"])
    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: cliente)

    with caplog.at_level("WARNING"):
        tokens = [t async for t in PerplexityProvider().stream("sonar-pro", "pergunta")]

    assert tokens[-1].tokens_out is None
    assert any("não devolveu usage" in r.getMessage() for r in caplog.records), (
        "o custo foi para zero sem nenhum aviso"
    )


async def test_nao_volta_a_fatiar_a_resposta_pronta():
    """Trava a correção: se alguém reintroduzir o `complete()` + fatiamento, o
    modo mais usado volta a fazer o médico esperar em tela parada."""
    fonte = inspect.getsource(PerplexityProvider.stream)

    assert "await self.complete(" not in fonte, (
        "o stream do Perplexity voltou a chamar complete() e fatiar o texto"
    )
    assert "aiter_lines" in fonte


async def test_o_timeout_da_assinatura_e_respeitado(monkeypatch):
    """A versão antiga declarava `timeout: int = 15` e passava 45 fixo para o
    `complete()` — quem pedisse 10s esperava 45."""
    fonte = inspect.getsource(PerplexityProvider.stream)

    assert "timeout=45" not in fonte, "o timeout voltou a ser fixo, ignorando o parâmetro"
    assert "timeout=timeout" in fonte


async def test_search_results_moderno_traz_o_titulo(monkeypatch):
    """
    A Perplexity expõe as mesmas fontes de duas formas: o array legado
    `citations`, só com URLs, e `search_results`, com `{title, url, date}`. O
    código lia apenas o legado — e a tela mostrava URL crua tendo o título
    disponível na mesma resposta.
    """
    cliente = _ClienteFake([
        _evento("texto", search_results=[
            {"url": "https://fonte.example", "title": "Um artigo de verdade"},
        ]),
        _evento(usage={"prompt_tokens": 10, "completion_tokens": 5}),
        "data: [DONE]",
    ])
    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: cliente)

    tokens = [t async for t in PerplexityProvider().stream("sonar-pro", "pergunta")]

    assert [(c.url, c.titulo) for c in tokens[-1].citations] == [
        ("https://fonte.example", "Um artigo de verdade")
    ]
