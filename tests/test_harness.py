"""
Testes do próprio harness (item 1.1 do plano de prontidão).

Se algum destes falhar, todos os testes de integração ficam sem valor: eles
estariam rodando contra o banco errado, sem isolamento entre testes, ou com
liberdade para chamar serviços externos de verdade.
"""

import pytest
from sqlalchemy import select

from app.models.models import User
from tests.conftest import TEST_DATABASE_URL, auth_headers


async def test_banco_de_teste_esta_isolado():
    """A trava do conftest apontou a aplicação para o banco de teste."""
    from app.core.config import get_settings

    assert get_settings().database_url == TEST_DATABASE_URL
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1]
    assert "rlwy.net" not in TEST_DATABASE_URL, "URL de produção vazou para os testes"


async def test_app_responde(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


async def test_usuario_autenticado_acessa_me(client, user):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["email"] == user.email


async def test_sem_token_recebe_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_token_malformado_recebe_401(client):
    """`sub` que não é UUID precisa dar 401, não 500 (regressão de app/api/deps.py)."""
    import jwt as pyjwt

    from app.core.config import get_settings

    settings = get_settings()
    token = pyjwt.encode({"sub": "nao-e-uuid"}, settings.jwt_secret_key, algorithm="HS256")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_fixture_admin_tem_papel(admin):
    assert admin.role == "admin"


# ── Isolamento entre testes ──────────────────────────────────────────────
# O par abaixo prova que o rollback funciona: o primeiro escreve, o segundo
# não pode enxergar. Se o isolamento quebrar, o segundo falha.

MARCADOR = "isolamento@example.com"


async def test_isolamento_parte1_escreve(db, user_factory):
    await user_factory(email=MARCADOR)
    achado = await db.execute(select(User).where(User.email == MARCADOR))
    assert achado.scalar_one_or_none() is not None


async def test_isolamento_parte2_nao_enxerga(db):
    achado = await db.execute(select(User).where(User.email == MARCADOR))
    assert achado.scalar_one_or_none() is None, (
        "Dado do teste anterior sobreviveu — o rollback da fixture `db` não está funcionando."
    )


# ── Guarda de rede ───────────────────────────────────────────────────────

async def test_chamada_externa_e_bloqueada():
    import httpx

    with pytest.raises(AssertionError, match="chamada HTTP externa"):
        async with httpx.AsyncClient() as c:
            await c.get("https://api.anthropic.com/v1/messages")


@pytest.mark.rede_real
async def test_marca_rede_real_desarma_a_guarda():
    """A marca existe para o caso raro de teste de contrato contra o serviço real."""
    import httpx

    assert httpx.AsyncHTTPTransport.handle_async_request.__name__ != "_proibido"


async def test_cliente_de_teste_nao_e_bloqueado_pela_guarda(client):
    """
    A guarda mira o transporte de rede, não o `AsyncClient`: o cliente de teste
    também é um AsyncClient, só que sobre ASGITransport. Se alguém voltar a
    patchar a classe inteira, este teste quebra junto com todos os de integração.
    """
    assert (await client.get("/api/v1/health")).status_code == 200
