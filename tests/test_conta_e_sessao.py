"""
Conta e sessão (fase 3 do plano de 2026-09-18).

Quatro defeitos que se combinavam num vazamento entre médicos:

1. `PATCH /auth/me` trocava o e-mail sem prova de posse do endereço novo.
2. Identidade da Waid divergente era "recusada" no log e ACEITA no código.
3. Um token válido gerava outro, para sempre: a sessão não tinha idade máxima.
4. Não existia logout no servidor — o cookie HttpOnly sobrevivia ao "Sair".

O cenário: o médico A põe o e-mail do colega V no próprio perfil. V entra pelo
embed, cai na conta de A, e as conversas clínicas de V se acumulam lá. A lê tudo,
mantendo a sessão viva indefinidamente. Os testes abaixo cortam cada elo.
"""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from sqlalchemy import select

from app.api.deps import COOKIE_NAME
from app.core.config import get_settings
from app.models.models import AuditLog
from app.services import auth_service
from app.services.integracoes import curseduca_service
from tests.conftest import auth_headers

ORIGEM = "https://adminportalmedico360.curseduca.pro"


def _claims(token: str) -> dict:
    s = get_settings()
    return pyjwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])


def _token_com(user, **claims) -> str:
    """Token assinado de verdade, com claims à escolha — para simular o passado."""
    s = get_settings()
    base = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(UTC) + timedelta(minutes=30),
        "tv": user.token_version or 0,
    }
    return pyjwt.encode({**base, **claims}, s.jwt_secret_key, algorithm=s.jwt_algorithm)


# ── 1. Troca de e-mail ───────────────────────────────────────────────────────

async def test_email_nao_pode_ser_trocado_pelo_perfil(client, db, user_factory):
    atacante = await user_factory(email="a@hospital.com", name="Dr. A")

    resp = await client.patch(
        "/api/v1/auth/me",
        json={"email": "colega.v@hospital.com"},
        headers=auth_headers(atacante),
    )

    assert resp.status_code == 409
    await db.refresh(atacante)
    assert atacante.email == "a@hospital.com", "o e-mail foi trocado sem prova de posse"


async def test_mandar_o_proprio_email_continua_aceito(client, user_factory):
    """Cliente antigo manda nome E e-mail no mesmo PATCH; não pode quebrar."""
    user = await user_factory(email="ana@hospital.com", name="Ana")

    resp = await client.patch(
        "/api/v1/auth/me",
        json={"name": "Ana Souza", "email": "Ana@Hospital.com"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 200


# ── 2. Identidade divergente ─────────────────────────────────────────────────

async def test_embed_com_identidade_divergente_nao_emite_sessao_e_audita(
    client, db, user_factory, monkeypatch
):
    dono = await user_factory(email="dono@hospital.com")
    dono.waid_uuid = "uuid-do-dono"
    await db.commit()

    async def troca(_token):
        return curseduca_service.IdentidadeWaid(
            uuid="uuid-de-outra-pessoa", nome="Outro", email="dono@hospital.com"
        )

    monkeypatch.setattr(curseduca_service, "trocar_token_de_identidade", troca)

    resp = await client.post(
        "/api/v1/auth/embed/token", json={"token": "qualquer"}, headers={"Origin": ORIGEM}
    )

    assert resp.status_code == 403
    assert "access_token" not in resp.text
    assert COOKIE_NAME not in resp.cookies

    registro = (
        await db.execute(
            select(AuditLog).where(AuditLog.action == "auth.identidade_divergente_recusada")
        )
    ).scalar_one()
    assert registro.user_id == dono.id, "a auditoria vai para a conta que foi protegida"
    assert registro.metadata_["waid_uuid_recebido"] == "uuid-de-outra-pessoa"


# ── 3. Idade máxima da sessão ────────────────────────────────────────────────

async def test_token_novo_nasce_com_auth_time_e_versao(user):
    claims = _claims(auth_service.create_access_token(user))

    assert abs(claims["auth_time"] - datetime.now(UTC).timestamp()) < 5
    assert claims["tv"] == 0


async def test_renovar_pelo_perfil_NAO_estica_a_sessao(client, user):
    """O elo que mantinha a sessão viva para sempre: token válido → token novo."""
    login_ha_20h = int((datetime.now(UTC) - timedelta(hours=20)).timestamp())
    antigo = _token_com(user, auth_time=login_ha_20h)

    resp = await client.patch(
        "/api/v1/auth/me", json={"name": "Nome Novo"},
        headers={"Authorization": f"Bearer {antigo}"},
    )

    assert resp.status_code == 200
    novo = _claims(resp.json()["access_token"])
    assert novo["auth_time"] == login_ha_20h, "a renovação zerou o relógio da sessão"
    # E o `exp` respeita o teto: faltam 4h para as 24h, não mais uma hora cheia
    # contada de um relógio reiniciado.
    assert novo["exp"] <= login_ha_20h + 24 * 3600


async def test_exp_nunca_passa_do_fim_da_sessao(user):
    login_ha_23h50 = int((datetime.now(UTC) - timedelta(hours=23, minutes=50)).timestamp())

    claims = _claims(auth_service.create_access_token(user, auth_time=login_ha_23h50))

    assert claims["exp"] == login_ha_23h50 + 24 * 3600


async def test_sessao_com_mais_de_24h_e_recusada(client, user):
    login_ha_25h = int((datetime.now(UTC) - timedelta(hours=25)).timestamp())
    vencido = _token_com(user, auth_time=login_ha_25h)  # `exp` ainda no futuro

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {vencido}"})

    assert resp.status_code == 401
    assert "expirada" in resp.json()["detail"].lower()


async def test_token_antigo_sem_as_marcas_continua_valendo(client, user):
    """Quem está logado no momento do deploy não é derrubado."""
    s = get_settings()
    legado = pyjwt.encode(
        {"sub": str(user.id), "role": user.role, "exp": datetime.now(UTC) + timedelta(minutes=30)},
        s.jwt_secret_key, algorithm=s.jwt_algorithm,
    )

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {legado}"})

    assert resp.status_code == 200


# ── 4. Logout no servidor ────────────────────────────────────────────────────

async def test_depois_de_sair_o_mesmo_token_leva_401(client, user):
    cabecalho = auth_headers(user)
    assert (await client.get("/api/v1/auth/me", headers=cabecalho)).status_code == 200

    saiu = await client.post("/api/v1/auth/logout", headers=cabecalho)
    depois = await client.get("/api/v1/auth/me", headers=cabecalho)

    assert saiu.status_code == 204
    assert depois.status_code == 401, (
        "O token sobreviveu ao logout — em estação compartilhada, o próximo usuário "
        "lê o histórico do anterior."
    )


async def test_logout_vale_para_o_cookie_que_o_javascript_nao_alcanca(client, user):
    """O caso real: cookie HttpOnly, sem header `Authorization`."""
    token = auth_service.create_access_token(user)
    client.cookies.set(COOKIE_NAME, token)
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    saiu = await client.post("/api/v1/auth/logout")

    apagou = saiu.headers["set-cookie"]
    assert COOKIE_NAME in apagou
    assert "max-age=0" in apagou.lower()
    assert "httponly" in apagou.lower()

    # Mesmo que alguém tenha guardado uma cópia do cookie antes do logout:
    client.cookies.set(COOKIE_NAME, token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_novo_login_depois_do_logout_funciona(client, db, user):
    await client.post("/api/v1/auth/logout", headers=auth_headers(user))
    await db.refresh(user)

    resp = await client.get("/api/v1/auth/me", headers=auth_headers(user))

    assert user.token_version == 1
    assert resp.status_code == 200


async def test_sair_sem_sessao_valida_tambem_responde_204(client):
    resp = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": "Bearer token-que-nao-vale"}
    )

    assert resp.status_code == 204
    assert COOKIE_NAME in resp.headers["set-cookie"]


async def test_logout_nao_derruba_a_sessao_de_outro_medico(client, user_factory):
    a = await user_factory()
    b = await user_factory()

    await client.post("/api/v1/auth/logout", headers=auth_headers(a))

    assert (await client.get("/api/v1/auth/me", headers=auth_headers(b))).status_code == 200


@pytest.mark.parametrize("origem", ["https://evil.com"])
async def test_logout_de_origem_hostil_e_barrado(client, user, origem):
    """Senão qualquer página deslogava o médico à força (CSRF de logout)."""
    resp = await client.post(
        "/api/v1/auth/logout", headers={**auth_headers(user), "Origin": origem}
    )

    assert resp.status_code == 403


async def test_revogar_false_apaga_so_o_cookie_e_mantem_as_outras_sessoes(client, db, user):
    """A entrada do embed descarta a sessão DESTE navegador sem derrubar as outras."""
    cabecalho = auth_headers(user)

    resp = await client.post("/api/v1/auth/logout?revogar=false", headers=cabecalho)

    assert resp.status_code == 204
    assert "max-age=0" in resp.headers["set-cookie"].lower()
    await db.refresh(user)
    assert user.token_version == 0
    assert (await client.get("/api/v1/auth/me", headers=cabecalho)).status_code == 200
