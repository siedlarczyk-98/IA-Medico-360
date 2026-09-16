"""
Streaming de Anthropic, OpenAI e Google — texto, tokens e fontes.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
`ai_providers.py` é o arquivo que TODA resposta atravessa, e os caminhos de
streaming dos três provedores estavam quase todos descobertos: só o Perplexity
tinha teste (`tests/test_perplexity_streaming.py`).

O risco ficou concreto em 2026-09-16, quando os oito pontos de extração de
citação foram reescritos para passar a carregar o título do artigo (que os
provedores sempre enviaram e o código descartava). Se o streaming da Anthropic
ou do Google tivesse quebrado naquela mudança, **nenhum teste teria falhado** —
a verificação foi por leitura, que é o que estes testes substituem.

Cada provedor tem uma forma de evento SSE completamente diferente:

| Provedor | Texto | Fim | Fontes |
|---|---|---|---|
| Anthropic | `content_block_delta` / `text_delta` | `message_delta` | `web_search_result_delta` |
| OpenAI | `response.output_text.delta` | `response.completed` | `annotations[].url_citation` |
| Google | `candidates[].content.parts[].text` | `finishReason` | `groundingChunks[].web` |

Essa divergência é o motivo de o teste existir por provedor, e não um genérico:
o que quebra é justamente o detalhe de formato de cada um.

O que se afirma em todos: o texto sai FATIADO na ordem (o médico vê a resposta
se formando), o token final traz a contagem para o custo, e as fontes chegam com
o título quando a API o manda.
"""

import json

import pytest

from app.services.integracoes.ai_providers import (
    AnthropicProvider,
    GeminiProvider,
    OpenAIProvider,
)

# ── Cliente SSE falso ────────────────────────────────────────────────────────

class _RespostaSSE:
    def __init__(self, linhas):
        self._linhas = linhas

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for linha in self._linhas:
            yield linha


class ClienteSSE:
    """
    Substitui `get_client()`. Guarda o corpo enviado para que os testes possam
    afirmar o payload além da resposta.
    """

    def __init__(self, linhas):
        self._linhas = linhas
        self.corpo = None
        self.url = None
        self.headers = None

    def stream(self, metodo, url, **kwargs):
        self.corpo = kwargs.get("json")
        self.url = url
        self.headers = kwargs.get("headers")
        linhas = self._linhas

        class _Ctx:
            async def __aenter__(self):
                return _RespostaSSE(linhas)

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def sse(corpo: dict) -> str:
    return "data: " + json.dumps(corpo)


@pytest.fixture
def instalar_cliente(monkeypatch):
    def _instalar(linhas) -> ClienteSSE:
        cliente = ClienteSSE(linhas)
        monkeypatch.setattr(
            "app.services.integracoes.ai_providers.get_client", lambda: cliente
        )
        return cliente

    return _instalar


# ── Anthropic ────────────────────────────────────────────────────────────────

def eventos_anthropic(pedacos, tokens_in=100, tokens_out=50, fontes=None):
    linhas = [sse({"type": "message_start", "message": {"usage": {"input_tokens": tokens_in}}})]
    for pedaco in pedacos:
        linhas.append(sse({
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": pedaco},
        }))
    for fonte in fontes or []:
        linhas.append(sse({
            "type": "content_block_delta",
            "delta": {"type": "web_search_result_delta", **fonte},
        }))
    linhas.append(sse({"type": "message_delta", "usage": {"output_tokens": tokens_out}}))
    return linhas


async def test_anthropic_entrega_o_texto_em_pedacos_na_ordem(instalar_cliente):
    """O streaming existe para o médico ver a resposta se formando; juntar tudo
    e entregar no fim anularia o recurso."""
    instalar_cliente(eventos_anthropic(["A varfarina ", "interage com ", "o AAS."]))

    tokens = [t async for t in AnthropicProvider().stream("claude-sonnet-5", "p")]

    assert [t.delta for t in tokens if t.delta] == [
        "A varfarina ", "interage com ", "o AAS."
    ]


async def test_anthropic_fecha_com_a_contagem_de_tokens(instalar_cliente):
    """Sem os tokens no final, o custo da interação vai a zero em silêncio."""
    instalar_cliente(eventos_anthropic(["texto"], tokens_in=120, tokens_out=45))

    tokens = [t async for t in AnthropicProvider().stream("claude-sonnet-5", "p")]

    final = tokens[-1]
    assert final.done is True
    assert final.tokens_in == 120
    assert final.tokens_out == 45


async def test_anthropic_traz_a_fonte_com_titulo(instalar_cliente):
    """
    O `web_search_result_delta` traz `title` além de `url`. Por muito tempo a
    extração pegava só a URL, e a tela mostrava o endereço cru no lugar do nome
    do artigo.
    """
    instalar_cliente(eventos_anthropic(
        ["texto"],
        fontes=[{"url": "https://pubmed.gov/1", "title": "2026 ESC Guidelines"}],
    ))

    tokens = [
        t async for t in AnthropicProvider().stream("claude-sonnet-5", "p", web_search=True)
    ]

    assert [(c.url, c.titulo) for c in tokens[-1].citations] == [
        ("https://pubmed.gov/1", "2026 ESC Guidelines")
    ]


async def test_anthropic_sem_busca_nao_inventa_fonte(instalar_cliente):
    """Fonte só existe quando houve busca — senão seria atribuir procedência a
    texto gerado de memória."""
    instalar_cliente(eventos_anthropic(["texto"]))

    tokens = [t async for t in AnthropicProvider().stream("claude-sonnet-5", "p")]

    assert tokens[-1].citations is None


async def test_anthropic_fonte_sem_url_e_descartada(instalar_cliente):
    """Um item de fonte sem link não tem o que mostrar."""
    instalar_cliente(eventos_anthropic(
        ["texto"],
        fontes=[{"title": "Sem link"}, {"url": "https://ok.com", "title": "Com link"}],
    ))

    tokens = [
        t async for t in AnthropicProvider().stream("claude-sonnet-5", "p", web_search=True)
    ]

    assert [c.url for c in tokens[-1].citations] == ["https://ok.com"]


async def test_anthropic_custo_de_busca_so_com_busca(instalar_cliente):
    """A busca web é cobrada à parte; contá-la sem ter havido busca infla o
    custo da interação."""
    instalar_cliente(eventos_anthropic(["texto"]))
    tokens = [t async for t in AnthropicProvider().stream("claude-sonnet-5", "p")]
    assert tokens[-1].search_cost_usd == 0.0

    instalar_cliente(eventos_anthropic(["texto"]))
    tokens = [
        t async for t in AnthropicProvider().stream("claude-sonnet-5", "p", web_search=True)
    ]
    assert tokens[-1].search_cost_usd > 0


async def test_anthropic_ignora_linha_que_nao_e_sse(instalar_cliente):
    """Keep-alives e linhas em branco chegam no meio do stream."""
    linhas = eventos_anthropic(["texto"])
    instalar_cliente(["", ": keep-alive", *linhas])

    tokens = [t async for t in AnthropicProvider().stream("claude-sonnet-5", "p")]

    assert [t.delta for t in tokens if t.delta] == ["texto"]


# ── OpenAI (Responses API, com busca) ────────────────────────────────────────

def eventos_openai(pedacos, tokens_in=80, tokens_out=30, anotacoes=None):
    linhas = [
        sse({"type": "response.output_text.delta", "delta": p}) for p in pedacos
    ]
    linhas.append(sse({
        "type": "response.completed",
        "response": {
            "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out},
            "output": [{"content": [{"annotations": anotacoes or []}]}],
        },
    }))
    return linhas


async def test_openai_entrega_o_texto_em_pedacos(instalar_cliente):
    instalar_cliente(eventos_openai(["Primeiro ", "segundo."]))

    tokens = [
        t async for t in OpenAIProvider().stream("gpt-5.4", "p", web_search=True)
    ]

    assert [t.delta for t in tokens if t.delta] == ["Primeiro ", "segundo."]


async def test_openai_fecha_com_a_contagem_de_tokens(instalar_cliente):
    instalar_cliente(eventos_openai(["texto"], tokens_in=200, tokens_out=90))

    tokens = [
        t async for t in OpenAIProvider().stream("gpt-5.4", "p", web_search=True)
    ]

    assert tokens[-1].done is True
    assert tokens[-1].tokens_in == 200
    assert tokens[-1].tokens_out == 90


async def test_openai_traz_a_fonte_com_titulo(instalar_cliente):
    """A annotation `url_citation` tem `title`, que a extração descartava."""
    instalar_cliente(eventos_openai(["texto"], anotacoes=[
        {"type": "url_citation", "url": "https://nejm.org/x", "title": "Um estudo"},
    ]))

    tokens = [
        t async for t in OpenAIProvider().stream("gpt-5.4", "p", web_search=True)
    ]

    assert [(c.url, c.titulo) for c in tokens[-1].citations] == [
        ("https://nejm.org/x", "Um estudo")
    ]


async def test_openai_ignora_anotacao_de_outro_tipo(instalar_cliente):
    """`annotations` carrega mais que citação (file_citation, por exemplo)."""
    instalar_cliente(eventos_openai(["texto"], anotacoes=[
        {"type": "file_citation", "file_id": "abc"},
        {"type": "url_citation", "url": "https://ok.com", "title": "Fonte"},
    ]))

    tokens = [
        t async for t in OpenAIProvider().stream("gpt-5.4", "p", web_search=True)
    ]

    assert len(tokens[-1].citations) == 1


async def test_openai_manda_max_output_tokens_na_responses_api(instalar_cliente):
    """
    A Responses API usa `max_output_tokens` — nem `max_tokens` nem
    `max_completion_tokens`. Três nomes para a mesma ideia em três APIs da mesma
    empresa é exatamente onde nascem os 400 silenciosos.
    """
    cliente = instalar_cliente(eventos_openai(["texto"]))

    [t async for t in OpenAIProvider().stream("gpt-5.4", "p", web_search=True)]

    assert "max_output_tokens" in cliente.corpo
    assert "max_tokens" not in cliente.corpo
    assert "max_completion_tokens" not in cliente.corpo


# ── Google ───────────────────────────────────────────────────────────────────

def eventos_google(pedacos, tokens_in=60, tokens_out=25, chunks=None):
    linhas = [
        sse({"candidates": [{"content": {"parts": [{"text": p}]}}]}) for p in pedacos
    ]
    final: dict = {
        "candidates": [{
            "content": {"parts": []},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": tokens_in, "candidatesTokenCount": tokens_out},
    }
    if chunks is not None:
        final["candidates"][0]["groundingMetadata"] = {"groundingChunks": chunks}
    linhas.append(sse(final))
    return linhas


async def test_google_entrega_o_texto_em_pedacos(instalar_cliente):
    instalar_cliente(eventos_google(["Parte um ", "parte dois."]))

    tokens = [t async for t in GeminiProvider().stream("gemini-2.5-flash", "p")]

    assert [t.delta for t in tokens if t.delta] == ["Parte um ", "parte dois."]


async def test_google_fecha_com_a_contagem_de_tokens(instalar_cliente):
    instalar_cliente(eventos_google(["texto"], tokens_in=70, tokens_out=35))

    tokens = [t async for t in GeminiProvider().stream("gemini-2.5-flash", "p")]

    assert tokens[-1].done is True
    assert tokens[-1].tokens_in == 70
    assert tokens[-1].tokens_out == 35


async def test_google_traz_a_fonte_com_titulo(instalar_cliente):
    """`groundingChunks[].web` tem `uri` E `title`."""
    instalar_cliente(eventos_google(["texto"], chunks=[
        {"web": {"uri": "https://who.int/x", "title": "OMS — dengue"}},
    ]))

    tokens = [
        t async for t in GeminiProvider().stream("gemini-2.5-flash", "p", web_search=True)
    ]

    assert [(c.url, c.titulo) for c in tokens[-1].citations] == [
        ("https://who.int/x", "OMS — dengue")
    ]


async def test_google_chunk_sem_uri_e_descartado(instalar_cliente):
    instalar_cliente(eventos_google(["texto"], chunks=[
        {"web": {"title": "Sem uri"}},
        {"web": {"uri": "https://ok.com"}},
    ]))

    tokens = [
        t async for t in GeminiProvider().stream("gemini-2.5-flash", "p", web_search=True)
    ]

    assert [c.url for c in tokens[-1].citations] == ["https://ok.com"]


async def test_google_so_fecha_no_finish_reason(instalar_cliente):
    """
    O token final do Google é disparado por `finishReason`, não por um evento
    próprio. Sem ele, o stream termina sem `done=True` e o custo nunca é
    registrado.
    """
    instalar_cliente([
        sse({"candidates": [{"content": {"parts": [{"text": "a"}]}}]}),
        sse({"candidates": [{"content": {"parts": [{"text": "b"}]}}]}),
    ])

    tokens = [t async for t in GeminiProvider().stream("gemini-2.5-flash", "p")]

    assert all(not t.done for t in tokens)


async def test_google_liga_a_ferramenta_de_busca_so_quando_pedido(instalar_cliente):
    cliente = instalar_cliente(eventos_google(["texto"]))
    [t async for t in GeminiProvider().stream("gemini-2.5-flash", "p")]
    assert "tools" not in cliente.corpo

    cliente = instalar_cliente(eventos_google(["texto"]))
    [t async for t in GeminiProvider().stream("gemini-2.5-flash", "p", web_search=True)]
    assert cliente.corpo["tools"] == [{"google_search": {}}]


# ── Invariantes comuns aos três ──────────────────────────────────────────────

async def test_erro_http_propaga_em_vez_de_virar_stream_vazio(instalar_cliente):
    """
    Um stream que falha precisa LEVANTAR.

    Se devolvesse vazio, o orquestrador gravaria uma resposta em branco como se
    fosse legítima — o mesmo erro de categoria que escondeu o bug do PubMed e
    que faz o PharmaDB dizer "nenhuma interação" quando a base caiu.
    """
    class ClienteQueFalha:
        def stream(self, metodo, url, **kwargs):
            class _Ctx:
                async def __aenter__(self):
                    raise RuntimeError("502 Bad Gateway")

                async def __aexit__(self, *a):
                    return False

            return _Ctx()

    import app.services.integracoes.ai_providers as mod

    original = mod.get_client
    mod.get_client = lambda: ClienteQueFalha()
    try:
        with pytest.raises(RuntimeError):
            [t async for t in AnthropicProvider().stream("claude-sonnet-5", "p")]
    finally:
        mod.get_client = original
