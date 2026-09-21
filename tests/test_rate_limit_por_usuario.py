"""
O rate limit conta por MÉDICO, não por endereço.

Um hospital inteiro sai por um IP só (NAT). Com a chave por IP, todos os médicos
de lá dividiam as mesmas 30 perguntas por minuto, e um plantão movimentado
derrubava o colega da sala ao lado com 429.

Todos os testes aqui saem do MESMO IP — o cliente ASGI —, que é exatamente a
condição do hospital.
"""

from starlette.requests import Request

from app.core.limiter import chave_do_limite
from tests.conftest import auth_headers

ROTA = "/api/v1/conversations"  # 60/minuto, autenticada, barata


def _requisicao(headers: dict[str, str] | None = None, cookie: str | None = None) -> Request:
    brutos = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if cookie:
        brutos.append((b"cookie", cookie.encode()))
    return Request({"type": "http", "headers": brutos, "client": ("203.0.113.7", 1234)})


async def test_dois_medicos_no_mesmo_ip_tem_cotas_separadas(client, user_factory):
    ana, bruno = await user_factory(), await user_factory()

    for _ in range(60):
        assert (await client.get(ROTA, headers=auth_headers(ana))).status_code == 200
    estourou = await client.get(ROTA, headers=auth_headers(ana))
    colega = await client.get(ROTA, headers=auth_headers(bruno))

    assert estourou.status_code == 429
    assert colega.status_code == 200, "o plantão da Ana derrubou o Bruno, no mesmo hospital"


async def test_a_chave_e_o_usuario_quando_ha_token(user):
    chave = chave_do_limite(_requisicao(auth_headers(user)))

    assert chave == f"user:{user.id}"


async def test_o_cookie_de_sessao_tambem_identifica(user):
    from app.api.deps import COOKIE_NAME
    from app.services import auth_service

    token = auth_service.create_access_token(user)

    assert chave_do_limite(_requisicao(cookie=f"{COOKIE_NAME}={token}")) == f"user:{user.id}"


def test_sem_token_a_chave_e_o_ip():
    assert chave_do_limite(_requisicao()) == "203.0.113.7"


def test_token_forjado_nao_escolhe_a_propria_chave():
    """Senão bastava inventar um `sub` por requisição para nunca ser limitado."""
    import jwt as pyjwt

    forjado = pyjwt.encode({"sub": "quem-eu-quiser"}, "segredo-errado-com-32-bytes-ou-mais!!", algorithm="HS256")

    assert chave_do_limite(_requisicao({"Authorization": f"Bearer {forjado}"})) == "203.0.113.7"


def test_o_nome_do_cookie_nao_divergiu():
    from app.api.deps import COOKIE_NAME
    from app.core.limiter import COOKIE_DE_SESSAO

    assert COOKIE_DE_SESSAO == COOKIE_NAME


def test_em_producao_o_contador_mora_no_redis(monkeypatch):
    """Em memória o limite vale por processo, e subir workers o multiplicaria."""
    from app.core import limiter as modulo

    class Producao:
        is_production = True
        redis_url = "redis://redis.interno:6379/0"

    monkeypatch.setattr(modulo, "get_settings", lambda: Producao())

    assert modulo._onde_contar() == "redis://redis.interno:6379/0"
