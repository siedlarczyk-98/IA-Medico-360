"""
`POST /orquestrador/query` está OBSOLETA e em observação.

O stream passou a atender os modos de farmácia, e o único chamador conhecido
sumiu. A rota não foi apagada porque não se sabe se existe chamador de fora do
monorepo: cada chamada deixa rastro, e o silêncio no log é o sinal para remover.
Estes testes garantem que o rastro existe — sem ele a "observação" não observa nada.
"""

import logging

from app.main import app
from tests.conftest import auth_headers


async def test_continua_funcionando_e_avisa_que_vai_sair(as_user):
    resp = await as_user.post("/api/v1/orquestrador/query", json={"prompt": "bom dia"})

    assert resp.status_code == 200
    assert resp.json()["mode"] == "OFF_TOPIC"  # atalho de saudação: sem chamada de modelo
    assert resp.headers["deprecation"] == "true"
    assert "/api/v1/orquestrador/stream" in resp.headers["link"]


async def test_cada_chamada_deixa_rastro_com_quem_chamou(client, user, caplog):
    with caplog.at_level(logging.WARNING, logger="app.api.v1.endpoints.orquestrador"):
        await client.post(
            "/api/v1/orquestrador/query",
            json={"prompt": "bom dia"},
            headers={**auth_headers(user), "User-Agent": "integracao-desconhecida/1.0"},
        )

    registro = next(r for r in caplog.records if "orquestrador_query_obsoleto" in r.getMessage())
    assert registro.user_id == str(user.id)
    assert registro.user_agent == "integracao-desconhecida/1.0"


def test_o_openapi_marca_a_rota_como_obsoleta():
    operacao = app.openapi()["paths"]["/api/v1/orquestrador/query"]["post"]

    assert operacao["deprecated"] is True
    assert app.openapi()["paths"]["/api/v1/orquestrador/stream"]["post"].get("deprecated") is not True
