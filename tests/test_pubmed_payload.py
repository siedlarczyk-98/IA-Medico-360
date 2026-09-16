"""
O payload que o `pubmed_service` manda à OpenAI.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
A validação PubMed ficou quebrada em produção durante toda a vida do arquivo por
um parâmetro errado: `max_tokens` num modelo da família gpt-5, que responde HTTP
400. O `except` amplo virava isso em "sem validação", a seção sumia da tela e
nenhum erro aparecia.

Os testes existentes não pegaram porque TODOS substituem `validate_with_pubmed`
por um dublê (`tests/test_orquestrador_stream.py`,
`tests/test_pos_processamento_background.py`) ou injetam `extra_metadata` à mão
(`tests/test_conversas_referencias.py`). Eles cobrem o que é feito com o
resultado; ninguém olhava a requisição.

O mesmo defeito já havia esvaziado a tabela `semantic_cache`. Duas vezes o mesmo
erro, em dois arquivos, é padrão — e o que impede a terceira é um teste que olhe
o corpo da requisição, não o resultado dela.
"""

import json

import httpx
import pytest

from app.services.integracoes import pubmed_service


def _cliente_que_captura(capturado: dict, resposta_json: object) -> httpx.AsyncClient:
    """
    Cliente que grava o corpo da requisição em vez de sair para a rede.

    Um transporte falso, e não um monkeypatch no método, para que o payload
    passe pela serialização de verdade do httpx — é exatamente ali que um
    parâmetro inválido continuaria invisível.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        capturado["corpo"] = json.loads(request.content)
        capturado["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(resposta_json)}}]},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


@pytest.mark.asyncio
async def test_usa_max_completion_tokens_e_nunca_max_tokens():
    """
    A regressão exata que derrubou a validação.

    Afirma os dois lados: que o parâmetro novo está lá E que o antigo não está.
    Só o primeiro deixaria passar um payload com ambos, que também é 400.
    """
    capturado: dict = {}
    async with _cliente_que_captura(capturado, ["Diretriz X 2024"]) as client:
        await pubmed_service._extract_citations(client, "texto clínico qualquer")

    corpo = capturado["corpo"]
    assert "max_tokens" not in corpo, (
        "a família gpt-5 rejeita `max_tokens` com HTTP 400 — ver o comentário "
        "no payload de `_extract_citations`"
    )
    assert corpo["max_completion_tokens"] > 0


@pytest.mark.asyncio
async def test_modelo_e_da_familia_que_exige_o_parametro_novo():
    """
    Amarra o par modelo↔parâmetro.

    Se alguém trocar o modelo por um da família antiga, `max_completion_tokens`
    passa a ser o errado — este teste falha e obriga a decisão consciente, em
    vez de deixar o par divergir em silêncio.
    """
    capturado: dict = {}
    async with _cliente_que_captura(capturado, []) as client:
        await pubmed_service._extract_citations(client, "texto")

    assert capturado["corpo"]["model"].startswith("gpt-5")


@pytest.mark.asyncio
async def test_extrai_as_citacoes_do_json_devolvido():
    """O caminho feliz — que o payload correto de fato produz citações."""
    capturado: dict = {}
    esperado = ["2022 AHA/ACC/HFSA Heart Failure Guideline", "Graus et al. Lancet Neurol 2016"]
    async with _cliente_que_captura(capturado, esperado) as client:
        citacoes = await pubmed_service._extract_citations(client, "resposta clínica")

    assert citacoes == esperado


@pytest.mark.asyncio
async def test_erro_http_propaga_para_o_chamador():
    """
    `_extract_citations` NÃO engole erro.

    Quem decide o fallback é `validate_with_pubmed`, uma camada acima, que loga
    em ERROR com o corpo da resposta. Se esta função passasse a devolver `[]` no
    erro, a falha voltaria a ser indistinguível de "nenhuma citação no texto" —
    que foi o que escondeu o bug original.
    """

    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "Unsupported parameter"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await pubmed_service._extract_citations(client, "texto")
