"""
Cabeçalhos de segurança da API, e credenciais de CORS só para quem autentica.

O DEA e as páginas de captação são públicos e nunca mandam cookie, mas recebiam
`Access-Control-Allow-Credentials: true` como os apps autenticados: um XSS numa
delas leria o histórico clínico do médico logado (item 47 da varredura).
"""

import pytest

from app.core.config import get_settings
from app.core.security_headers import origens_sem_credenciais

ROTA = "/api/v1/health"


async def _com_origem(client, origem: str):
    return await client.get(ROTA, headers={"Origin": origem})


@pytest.mark.parametrize("campo", ["frontend_url", "calculadoras_url", "noticias_url"])
async def test_app_que_autentica_continua_com_credenciais(client, campo):
    origem = getattr(get_settings(), campo)

    resp = await _com_origem(client, origem)

    assert resp.headers["access-control-allow-origin"] == origem
    assert resp.headers["access-control-allow-credentials"] == "true"


async def test_dea_le_a_resposta_mas_sem_credenciais(client):
    origem = get_settings().dea_url

    resp = await _com_origem(client, origem)

    # Continua podendo LER (o app público precisa disso)...
    assert resp.headers["access-control-allow-origin"] == origem
    # ...mas o navegador não entrega a ele resposta de requisição feita com cookie.
    assert "access-control-allow-credentials" not in resp.headers


async def test_pagina_de_captacao_tambem_fica_sem_credenciais(client):
    origem = get_settings().landing_pages_origins[0]

    resp = await _com_origem(client, origem)

    assert resp.headers["access-control-allow-origin"] == origem
    assert "access-control-allow-credentials" not in resp.headers


async def test_preflight_de_origem_publica_tambem_sai_sem_credenciais(client):
    resp = await client.options(
        "/api/v1/dea/locais",
        headers={
            "Origin": get_settings().dea_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert resp.status_code == 200
    assert "access-control-allow-credentials" not in resp.headers


def test_nenhum_app_que_autentica_esta_na_lista_sem_credenciais():
    """Se um deles cair aqui, o login por cookie para de funcionar em silêncio."""
    s = get_settings()
    sem = origens_sem_credenciais(s)

    for campo in ("frontend_url", "calculadoras_url", "noticias_url"):
        assert getattr(s, campo) not in sem, campo


async def test_toda_resposta_traz_os_cabecalhos_de_seguranca(client):
    resp = await client.get(ROTA)

    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]
    assert resp.headers["cache-control"] == "no-store"


async def test_resposta_de_erro_tambem_traz(client):
    resp = await client.get("/api/v1/auth/me")  # 401

    assert resp.status_code == 401
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_historico_clinico_nao_fica_em_cache(client, user):
    from tests.conftest import auth_headers

    resp = await client.get("/api/v1/conversations", headers=auth_headers(user))

    assert resp.headers["cache-control"] == "no-store"


async def test_rota_que_define_o_proprio_cache_control_e_respeitada(client):
    """O stream manda `no-cache`; o middleware não pode sobrescrever."""
    from app.core.security_headers import CabecalhosDeSegurancaMiddleware

    enviados = []

    async def app_falso(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [(b"cache-control", b"no-cache")]})
        await send({"type": "http.response.body", "body": b""})

    async def send(m):
        enviados.append(m)

    mw = CabecalhosDeSegurancaMiddleware(app_falso, settings=get_settings())
    await mw({"type": "http", "path": "/x", "headers": []}, None, send)

    valores = [v for k, v in enviados[0]["headers"] if k == b"cache-control"]
    assert valores == [b"no-cache"]


def test_hsts_so_em_producao():
    from app.core.security_headers import CabecalhosDeSegurancaMiddleware

    assert CabecalhosDeSegurancaMiddleware(None, settings=get_settings()).hsts is False
