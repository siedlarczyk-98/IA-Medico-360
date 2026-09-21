"""
O preflight de CORS é cacheado pelo browser por 24h.

Sem `max_age` explícito o Starlette responde 600s, e toda chamada com
`Authorization` paga um OPTIONS a mais a cada dez minutos, por rota. Com a
latência do modelo fixa, é ida e volta desperdiçada antes de cada pergunta.
"""

from app.core.config import get_settings


async def _preflight(client, origem: str):
    return await client.options(
        "/api/v1/conversations",
        headers={
            "Origin": origem,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )


async def test_preflight_da_origem_do_app_e_cacheado_por_24h(client):
    resp = await _preflight(client, get_settings().frontend_url)

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == get_settings().frontend_url
    assert resp.headers["access-control-max-age"] == "86400"


async def test_preflight_de_origem_estranha_continua_recusado(client):
    """O cache longo não pode ter afrouxado quem passa no preflight."""
    resp = await _preflight(client, "https://evil.com")

    assert resp.status_code == 400
    assert "access-control-allow-origin" not in resp.headers
