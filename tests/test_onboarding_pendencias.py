"""
O onboarding depois que a especialidade passou a chegar sozinha.

O formulário deixou de ter um conjunto fixo de campos obrigatórios. Nome e
especialidade vêm do cadastro (webhook) ou dos grupos `[CFM]` da Curseduca;
pedir de novo o que já se sabe era metade do peso da tela. Agora o cliente manda
o que coletou e QUEM DECIDE se o perfil está completo é
`identidade.pendencias()`, no servidor, com o estado real do usuário.

Esses testes existem porque a mudança tirou validação do schema. Sem eles, a
regra passaria a morar só na tela — e a tela agora são três apps.
"""

from app.medicina import identidade
from tests.conftest import auth_headers


def _payload(**extra) -> dict:
    """O formulário enxuto: estágio de carreira + aceite."""
    base = {"med_status": "especialista", "terms_accepted": True}
    base.update(extra)
    return base


async def test_especialista_com_especialidade_automatica_nao_precisa_informar(
    client, db, user
):
    """O caso que motivou a mudança.

    O médico entrou pelo embed, o grupo `[CFM] Cardiologia` já preencheu a
    especialidade. Ele não deve ter que escolhê-la de novo num dropdown.
    """
    identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_WAID_GRUPO
    )
    user.crm, user.crm_state = "123456", "SP"
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user)
    )

    assert resp.status_code == 200
    assert resp.json()["onboarding_complete"] is True
    assert resp.json()["onboarding_pendencias"] == []


async def test_perfil_incompleto_nao_marca_completo_e_diz_o_que_falta(client, user):
    """Sem especialidade, o onboarding aceita o progresso parcial.

    Recusar com 422 perderia o aceite dos Termos que o médico acabou de dar; o
    servidor grava o que veio e devolve o que ainda falta, para a tela
    continuar de onde parou.

    Note que CRM NÃO aparece: deixou de ser pendência quando ficou claro que a
    prova de registro vem do grupo `[CFM]`, não de um campo digitado.
    """
    resp = await client.post(
        "/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user)
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["onboarding_complete"] is False
    assert corpo["onboarding_pendencias"] == ["especialidade"]


async def test_crm_nao_bloqueia_mais_o_onboarding(client, db, user):
    """Especialista com especialidade e SEM CRM completa o cadastro.

    Antes o CRM era exigido de todo médico formado. A prova de registro passou a
    vir do grupo `[CFM]` criado pela página de cadastro, que consultou o
    Conselho — um número digitado à mão não acrescentava prova nenhuma.
    """
    identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_WAID_GRUPO
    )
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user)
    )

    assert resp.status_code == 200
    assert resp.json()["onboarding_complete"] is True
    await db.refresh(user)
    assert user.crm is None  # segue vazio, e está tudo bem


async def test_especialidade_digitada_nao_sobrescreve_a_automatica(client, db, user):
    """Fallback é fallback: se o grupo já preencheu, o que veio da tela é ignorado.

    O campo é identidade profissional e vai definir acesso — a precedência de
    `identidade.py` manda, mesmo que o cliente insista.
    """
    identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_CADASTRO
    )
    user.crm, user.crm_state = "123456", "SP"
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/onboarding",
        json=_payload(specialty="Nefrologia"),
        headers=auth_headers(user),
    )

    assert resp.status_code == 200
    await db.refresh(user)
    assert user.specialty_slug == "cardiologia"
    assert user.specialty_source == identidade.FONTE_CADASTRO


async def test_especialidade_digitada_vale_quando_nao_ha_fonte_automatica(
    client, db, user
):
    """A base antiga: ninguém preencheu por ele, então o que ele digita vale."""
    user.crm, user.crm_state = "123456", "SP"
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/onboarding",
        json=_payload(specialty="Nefrologia"),
        headers=auth_headers(user),
    )

    assert resp.status_code == 200
    assert resp.json()["onboarding_complete"] is True
    await db.refresh(user)
    assert user.specialty_slug == "nefrologia"
    assert user.specialty_source == identidade.FONTE_DECLARADO


async def test_graduando_completa_sem_crm_nem_especialidade(client, user):
    """Não é cadastro pela metade: é o estado correto de quem ainda não se formou."""
    resp = await client.post(
        "/api/v1/auth/onboarding",
        json=_payload(med_status="graduando", enrollment_year=2022),
        headers=auth_headers(user),
    )

    assert resp.status_code == 200
    assert resp.json()["onboarding_complete"] is True


async def test_generalista_completa_sem_especialidade(client, user):
    resp = await client.post(
        "/api/v1/auth/onboarding",
        json=_payload(med_status="generalista", crm="123456", crm_state="SP"),
        headers=auth_headers(user),
    )

    assert resp.status_code == 200
    assert resp.json()["onboarding_complete"] is True


async def test_telefone_deixou_de_ser_obrigatorio(client, db, user):
    """Saiu do formulário para reduzir atrito; a WAID já traz `phones`."""
    identidade.aplicar_especialidade(
        user, slug="cardiologia", fonte=identidade.FONTE_WAID_GRUPO
    )
    user.crm, user.crm_state = "123456", "SP"
    await db.flush()

    resp = await client.post(
        "/api/v1/auth/onboarding", json=_payload(), headers=auth_headers(user)
    )

    assert resp.status_code == 200
    await db.refresh(user)
    assert user.phone_number is None


async def test_crm_sem_uf_e_recusado(client, user):
    """A única regra condicional que sobrou no schema — não depende do usuário."""
    resp = await client.post(
        "/api/v1/auth/onboarding",
        json=_payload(crm="123456"),
        headers=auth_headers(user),
    )
    assert resp.status_code == 422


async def test_aceite_continua_obrigatorio(client, user):
    """A garantia da LGPD não pode ter regredido com o relaxamento do schema."""
    resp = await client.post(
        "/api/v1/auth/onboarding",
        json=_payload(terms_accepted=False),
        headers=auth_headers(user),
    )
    assert resp.status_code == 422
