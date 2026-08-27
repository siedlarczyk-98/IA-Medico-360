"""
Registro de consentimento (LGPD art. 8).

O checkbox "Li e aceito" já existia no onboarding, mas só habilitava o botão: o
valor nunca chegava ao backend e nada era gravado. Como o ônus da prova é do
controlador (art. 8, §2º), isso equivalia a não ter consentimento nenhum.

Estes testes cobrem o que sustenta a prova: que o aceite vira registro, que o
onboarding é recusado sem ele, e que a revogação não apaga o histórico.
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.models import ConsentLog
from app.services import consent_service
from tests.conftest import auth_headers


def _payload(**extra) -> dict:
    base = {
        "name": "Ana Ribeiro",
        "phone_number": "11999998888",
        "med_status": "especialista",
        "crm": "123456",
        "crm_state": "SP",
        "specialty": "Cardiologia",
        "terms_accepted": True,
    }
    base.update(extra)
    return base


async def test_onboarding_grava_o_aceite(client, db, user):
    resp = await client.post("/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user))
    assert resp.status_code == 200

    registros = (await db.execute(select(ConsentLog).where(ConsentLog.user_id == user.id))).scalars().all()
    assert len(registros) == 1
    registro = registros[0]
    assert registro.accepted is True
    assert registro.accepted_at is not None
    assert registro.revoked_at is None
    # A versao acompanha o registro: consentir com um documento que muda depois
    # nao prova nada sobre o texto vigente.
    assert registro.consent_type == f"{consent_service.TERMOS_E_PRIVACIDADE}@{consent_service.VERSAO_DOCUMENTOS}"


async def test_onboarding_recusado_sem_aceite(client, db, user):
    """
    A validacao vive no servidor, nao no botao desabilitado: o endpoint e
    publico e o cliente pode nao ser a nossa tela.
    """
    resp = await client.post(
        "/api/v1/auth/onboarding", json=_payload(terms_accepted=False), headers=auth_headers(user)
    )
    assert resp.status_code == 422
    assert (await db.execute(select(ConsentLog))).scalars().first() is None


async def test_onboarding_recusado_se_o_campo_nem_vier(client, db, user):
    """Sem default no schema: cliente que esquece de enviar falha, nao passa batido."""
    corpo = _payload()
    del corpo["terms_accepted"]
    resp = await client.post("/api/v1/auth/onboarding", json=corpo, headers=auth_headers(user))
    assert resp.status_code == 422
    assert (await db.execute(select(ConsentLog))).scalars().first() is None


async def test_usuario_sem_onboarding_nao_tem_consentimento(client, user):
    resp = await client.get("/api/v1/auth/me/consentimentos", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["consentimentos"] == {}


async def test_situacao_reflete_o_aceite(client, user):
    await client.post("/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user))

    corpo = (await client.get("/api/v1/auth/me/consentimentos", headers=auth_headers(user))).json()
    atual = corpo["consentimentos"][consent_service.TERMOS_E_PRIVACIDADE]
    assert atual["aceito"] is True
    assert atual["versao_atual"] is True
    assert corpo["versao_vigente"] == consent_service.VERSAO_DOCUMENTOS


async def test_aceite_de_versao_antiga_aparece_como_desatualizado(client, db, user, monkeypatch):
    """
    Ao publicar uma revisao dos documentos, quem aceitou a anterior nao pode
    parecer que consentiu com o texto novo.
    """
    await client.post("/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user))
    monkeypatch.setattr(consent_service, "VERSAO_DOCUMENTOS", "2027-01")

    atual = await consent_service.situacao_atual(db, user.id)
    assert atual[consent_service.TERMOS_E_PRIVACIDADE]["versao_atual"] is False


async def test_termos_nao_sao_revogaveis_por_esta_rota(client, user):
    """Sem termos nao ha servico; o caminho e excluir a conta, que apaga os dados."""
    await client.post("/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user))
    resp = await client.post(
        f"/api/v1/auth/me/consentimentos/{consent_service.TERMOS_E_PRIVACIDADE}/revogar",
        headers=auth_headers(user),
    )
    assert resp.status_code == 400
    assert "exclua a conta" in resp.json()["detail"]


async def test_revogacao_preserva_o_aceite_anterior(client, db, user):
    """
    Revogar grava uma nova manifestacao negativa. Sobrescrever destruiria a
    evidencia de que houve aceite valido enquanto os dados foram tratados.
    """
    await consent_service.registrar(db, user, consent_service.USO_DADOS_ANONIMIZADOS, aceito=True)
    await db.commit()

    resp = await client.post(
        f"/api/v1/auth/me/consentimentos/{consent_service.USO_DADOS_ANONIMIZADOS}/revogar",
        headers=auth_headers(user),
    )
    assert resp.status_code == 204

    registros = await consent_service.historico(db, user.id)
    assert len(registros) == 2
    assert registros[0].accepted is False and registros[0].revoked_at is not None
    assert registros[1].accepted is True  # o aceite original continua la

    atual = await consent_service.situacao_atual(db, user.id)
    assert atual[consent_service.USO_DADOS_ANONIMIZADOS]["aceito"] is False


async def test_revogar_tipo_desconhecido_da_404(client, user):
    resp = await client.post(
        "/api/v1/auth/me/consentimentos/qualquer_coisa/revogar", headers=auth_headers(user)
    )
    assert resp.status_code == 404


@pytest.mark.parametrize("rota", ["/api/v1/auth/me/consentimentos"])
async def test_consentimento_exige_autenticacao(client, rota):
    assert (await client.get(rota)).status_code == 401


def test_versao_dos_documentos_bate_com_o_frontend():
    """
    As duas constantes precisam andar juntas. Se o front linkar uma revisao nova
    e o backend continuar gravando a antiga, o registro passa a afirmar que o
    usuario aceitou um texto que ele nunca viu - e o registro so vale pelo que
    consegue provar.
    """
    arquivo = Path(__file__).resolve().parents[1] / "frontend-app" / "src" / "lib" / "documentos.ts"
    achado = re.search(r"VERSAO_DOCUMENTOS\s*=\s*'([^']+)'", arquivo.read_text(encoding="utf-8"))
    assert achado, "VERSAO_DOCUMENTOS nao encontrada em documentos.ts"
    assert achado.group(1) == consent_service.VERSAO_DOCUMENTOS


async def test_ordem_do_historico_e_estavel_com_timestamps_identicos(db, user):
    """
    `created_at` sozinho não define ordem total. Este teste força o empate que
    na prática é raro — dois registros no mesmo instante — e exige que a
    revogação venha antes do aceite.

    Num histórico com valor probatório, "aceitou e depois revogou" e "revogou e
    depois aceitou" são fatos opostos; ordem arbitrária entre eles é inaceitável.
    """
    from datetime import UTC, datetime

    from app.models.models import ConsentLog

    instante = datetime.now(UTC)
    tipo = f"{consent_service.USO_DADOS_ANONIMIZADOS}@teste"

    db.add(ConsentLog(
        user_id=user.id, consent_type=tipo, accepted=True,
        accepted_at=instante, revoked_at=None, created_at=instante,
    ))
    db.add(ConsentLog(
        user_id=user.id, consent_type=tipo, accepted=False,
        accepted_at=None, revoked_at=instante, created_at=instante,
    ))
    await db.flush()

    for _ in range(5):
        registros = await consent_service.historico(db, user.id)
        assert registros[0].accepted is False, "revogação deve vir primeiro"
        assert registros[1].accepted is True
