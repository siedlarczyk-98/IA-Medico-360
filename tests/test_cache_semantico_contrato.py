"""
Contrato do cache semântico com a API da OpenAI.

Existe por um bug que passou despercebido em produção: `_normalize_prompt`
mandava `max_tokens`, que a família gpt-5 recusa com HTTP 400. O erro caía no
`except` genérico de `get_cached_response`, virava um `logger.warning` e a
função devolvia MISS — o comportamento normal de quem não achou nada.

O resultado é o pior tipo de falha: nada quebra, nada alerta, e o cache
simplesmente nunca funciona. A tabela `semantic_cache` ficou com zero linhas e
a taxa de acerto em 0% enquanto tudo parecia saudável. Cada requisição ainda
pagava a chamada que falhava, no caminho do primeiro token.

Estes testes fixam o formato do payload. Nenhum toca a rede.
"""

import httpx
import pytest

from app.services import semantic_cache_service as cache


class RespostaFalsa:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "erro", request=httpx.Request("POST", "https://api.openai.com"),
                response=httpx.Response(self.status_code, text=self.text),
            )


class ClienteFalso:
    """Registra o que foi enviado e devolve respostas roteadas por URL."""

    def __init__(self, status_normalize=200):
        self.enviados: list[tuple[str, dict]] = []
        self.status_normalize = status_normalize

    async def post(self, url, **kwargs):
        payload = kwargs.get("json", {})
        self.enviados.append((url, payload))

        if "chat/completions" in url:
            return RespostaFalsa(
                {"choices": [{"message": {
                    "content": '{"cacheable": true, "normalized_prompt": "posologia de amoxicilina"}'
                }}]},
                status=self.status_normalize,
            )
        return RespostaFalsa({"data": [{"embedding": [0.1] * cache.EMBEDDING_DIMS}]})


@pytest.fixture(autouse=True)
def sem_redis(monkeypatch):
    async def _nada(*a, **k):
        return None
    monkeypatch.setattr("app.services.cache_service.get_json", _nada)
    monkeypatch.setattr("app.services.cache_service.set_json", _nada)


def payload_de(cliente, fragmento_url):
    return next(p for url, p in cliente.enviados if fragmento_url in url)


async def test_normalizacao_usa_max_completion_tokens(db, monkeypatch):
    """
    `max_tokens` é recusado pela família gpt-5 com HTTP 400. Este é o parâmetro
    que desligou o cache inteiro sem produzir um erro visível.
    """
    cliente = ClienteFalso()
    monkeypatch.setattr(cache, "get_client", lambda: cliente)

    await cache.get_cached_response(db, "QUICK_SEARCH", "posologia de amoxicilina?")

    enviado = payload_de(cliente, "chat/completions")
    assert "max_completion_tokens" in enviado
    assert "max_tokens" not in enviado, (
        "a família gpt-5 recusa `max_tokens` com 400 — foi o bug original"
    )


async def test_miss_devolve_normalizado_e_embedding_para_o_store(db, monkeypatch):
    """
    No MISS a função precisa devolver normalizado + embedding: é com eles que o
    caller grava a resposta depois. Devolvendo vazio, `store_response` sai pela
    guarda inicial e o cache nunca é escrito — que era o efeito do 400.
    """
    cliente = ClienteFalso()
    monkeypatch.setattr(cache, "get_client", lambda: cliente)

    cached, normalizado, embedding = await cache.get_cached_response(
        db, "QUICK_SEARCH", "posologia de amoxicilina?"
    )

    assert cached is None, "cache vazio, deveria ser MISS"
    assert normalizado, "sem prompt normalizado o store é pulado"
    assert len(embedding) == cache.EMBEDDING_DIMS


async def test_erro_http_na_normalizacao_nao_derruba_a_resposta(db, monkeypatch):
    """
    Falhar sem cache continua sendo o comportamento certo — o médico recebe a
    resposta. O que não pode é falhar sem deixar rastro.
    """
    cliente = ClienteFalso(status_normalize=400)
    monkeypatch.setattr(cache, "get_client", lambda: cliente)

    cached, normalizado, embedding = await cache.get_cached_response(
        db, "QUICK_SEARCH", "posologia de amoxicilina?"
    )

    assert cached is None
    assert normalizado == ""
    assert embedding == []


async def test_erro_http_e_registrado_com_status_e_corpo(db, monkeypatch, caplog):
    """Sem status e corpo no log, um defeito de contrato é indistinguível de
    'não achei nada no cache' — foi assim que ele sobreviveu em produção."""
    cliente = ClienteFalso(status_normalize=400)
    monkeypatch.setattr(cache, "get_client", lambda: cliente)

    with caplog.at_level("WARNING"):
        await cache.get_cached_response(db, "QUICK_SEARCH", "posologia?")

    assert any("400" in r.getMessage() for r in caplog.records), caplog.text


async def test_store_ignorado_sem_normalizado_ou_embedding(db):
    """A guarda que transformou o 400 em cache permanentemente vazio."""
    from sqlalchemy import text as sql

    await cache.store_response(db, "QUICK_SEARCH", "", [], {"status": "ok"})
    await cache.store_response(db, "QUICK_SEARCH", "algo", [], {"status": "ok"})

    total = (await db.execute(sql("SELECT COUNT(*) FROM semantic_cache"))).scalar_one()
    assert total == 0


async def test_store_grava_quando_ha_normalizado_e_embedding(db):
    from sqlalchemy import text as sql

    await cache.store_response(
        db, "QUICK_SEARCH", "posologia de amoxicilina",
        [0.1] * cache.EMBEDDING_DIMS, {"status": "ok", "response_text": "500mg"},
    )

    total = (await db.execute(sql("SELECT COUNT(*) FROM semantic_cache"))).scalar_one()
    assert total == 1
