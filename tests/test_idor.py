"""
Isolamento entre contas — IDOR (item 1.2 do plano de prontidão).

Cada teste monta dois usuários, cria um recurso para o `dono` e tenta alcançá-lo
com o token do `intruso`. É o cenário de maior custo do produto: vazamento de
histórico clínico entre contas.

Convenção de resposta: **404, não 403**. Confirmar a existência de um recurso
alheio já é vazamento de informação — o intruso não deve conseguir distinguir
"existe mas não é seu" de "não existe".
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.models import Folder
from tests.conftest import auth_headers

UUID_INEXISTENTE = "00000000-0000-0000-0000-00000000dead"


@pytest.fixture
async def dono(user_factory):
    return await user_factory(email="dono@example.com")


@pytest.fixture
async def intruso(user_factory):
    return await user_factory(email="intruso@example.com")


# ── Conversas ────────────────────────────────────────────────────────────

async def test_intruso_nao_le_conversa_alheia(client, dono, intruso, conversation_factory):
    conv = await conversation_factory(dono, title="Caso clínico confidencial")

    resp = await client.get(
        f"/api/v1/conversations/{conv.id}", headers=auth_headers(intruso)
    )

    assert resp.status_code == 404
    assert "confidencial" not in resp.text


async def test_dono_le_a_propria_conversa(client, dono, conversation_factory):
    """Contraprova: se este falhar, o teste acima passaria por engano."""
    conv = await conversation_factory(dono)
    resp = await client.get(f"/api/v1/conversations/{conv.id}", headers=auth_headers(dono))
    assert resp.status_code == 200


async def test_listagem_de_conversas_so_traz_as_proprias(
    client, dono, intruso, conversation_factory
):
    await conversation_factory(dono, title="Do dono")
    await conversation_factory(intruso, title="Do intruso")

    resp = await client.get("/api/v1/conversations", headers=auth_headers(intruso))

    assert resp.status_code == 200
    titulos = resp.text
    assert "Do intruso" in titulos
    assert "Do dono" not in titulos


# ── Pastas ───────────────────────────────────────────────────────────────

async def test_intruso_nao_renomeia_pasta_alheia(client, db, dono, intruso, folder_factory):
    pasta = await folder_factory(dono, name="Original")

    resp = await client.put(
        f"/api/v1/folders/{pasta.id}",
        json={"name": "Invadida"},
        headers=auth_headers(intruso),
    )

    assert resp.status_code == 404
    await db.refresh(pasta)
    assert pasta.name == "Original", "A pasta do dono foi alterada por outro usuário"


async def test_intruso_nao_apaga_pasta_alheia(client, db, dono, intruso, folder_factory):
    pasta = await folder_factory(dono)

    resp = await client.delete(f"/api/v1/folders/{pasta.id}", headers=auth_headers(intruso))

    assert resp.status_code == 404
    ainda_existe = await db.execute(select(Folder).where(Folder.id == pasta.id))
    assert ainda_existe.scalar_one_or_none() is not None, "A pasta do dono foi apagada"


async def test_listagem_de_pastas_so_traz_as_proprias(
    client, dono, intruso, folder_factory
):
    await folder_factory(dono, name="Pasta do dono")
    await folder_factory(intruso, name="Pasta do intruso")

    resp = await client.get("/api/v1/folders", headers=auth_headers(intruso))

    assert resp.status_code == 200
    assert "Pasta do intruso" in resp.text
    assert "Pasta do dono" not in resp.text


# ── Mover conversa entre pastas ──────────────────────────────────────────

async def test_intruso_nao_move_conversa_alheia(
    client, db, dono, intruso, conversation_factory, folder_factory
):
    conv = await conversation_factory(dono)
    pasta_do_intruso = await folder_factory(intruso)

    resp = await client.patch(
        f"/api/v1/folders/conversations/{conv.id}/folder",
        json={"folder_id": str(pasta_do_intruso.id)},
        headers=auth_headers(intruso),
    )

    assert resp.status_code == 404
    await db.refresh(conv)
    assert conv.folder_id is None, "Conversa alheia foi movida para a pasta do intruso"


async def test_intruso_nao_move_conversa_propria_para_pasta_alheia(
    client, db, dono, intruso, conversation_factory, folder_factory
):
    """O outro lado do mesmo fluxo: a pasta de destino também precisa ser sua."""
    conv = await conversation_factory(intruso)
    pasta_do_dono = await folder_factory(dono)

    resp = await client.patch(
        f"/api/v1/folders/conversations/{conv.id}/folder",
        json={"folder_id": str(pasta_do_dono.id)},
        headers=auth_headers(intruso),
    )

    assert resp.status_code == 404
    await db.refresh(conv)
    assert conv.folder_id is None


async def test_bulk_move_ignora_conversas_alheias(
    client, db, dono, intruso, conversation_factory, folder_factory
):
    """
    O bulk usa UPDATE ... WHERE id IN (...) AND user_id = :eu.
    Mandar ids alheios não pode mover nada — e não deve dar erro que revele
    quais ids existem.
    """
    conv_do_dono = await conversation_factory(dono)
    conv_do_intruso = await conversation_factory(intruso)
    pasta_do_intruso = await folder_factory(intruso)

    resp = await client.patch(
        "/api/v1/folders/conversations/bulk",
        json={
            "conversation_ids": [str(conv_do_dono.id), str(conv_do_intruso.id)],
            "folder_id": str(pasta_do_intruso.id),
        },
        headers=auth_headers(intruso),
    )

    assert resp.status_code == 204
    await db.refresh(conv_do_dono)
    await db.refresh(conv_do_intruso)
    assert conv_do_dono.folder_id is None, "Conversa alheia foi movida no bulk"
    assert conv_do_intruso.folder_id == pasta_do_intruso.id


# ── Recurso inexistente responde igual a recurso alheio ──────────────────

@pytest.mark.parametrize(
    ("metodo", "template"),
    [
        ("GET", "/api/v1/conversations/{}"),
        ("PUT", "/api/v1/folders/{}"),
        ("DELETE", "/api/v1/folders/{}"),
    ],
)
async def test_alheio_e_inexistente_sao_indistinguiveis(
    client, dono, intruso, conversation_factory, folder_factory, metodo, template
):
    """
    Se recurso alheio desse 403 e inexistente desse 404, dava para enumerar ids
    válidos comparando as respostas. Os dois casos precisam ser idênticos.
    """
    alheio = (
        await conversation_factory(dono)
        if "conversations" in template
        else await folder_factory(dono)
    )
    corpo = {"name": "x"} if metodo == "PUT" else None

    r_alheio = await client.request(
        metodo, template.format(alheio.id), json=corpo, headers=auth_headers(intruso)
    )
    r_inexistente = await client.request(
        metodo, template.format(UUID_INEXISTENTE), json=corpo, headers=auth_headers(intruso)
    )

    assert r_alheio.status_code == r_inexistente.status_code == 404
    assert r_alheio.json() == r_inexistente.json()


# ── Histórico do agregador ───────────────────────────────────────────────

async def test_historico_do_agregador_e_por_usuario(client, dono, intruso):
    resp = await client.get("/api/v1/agregador/history", headers=auth_headers(intruso))
    assert resp.status_code == 200
    assert "dono@example.com" not in resp.text


# ── Conta ────────────────────────────────────────────────────────────────

async def test_me_devolve_apenas_o_proprio_usuario(client, dono, intruso):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(intruso))
    assert resp.status_code == 200
    assert resp.json()["email"] == intruso.email


async def test_patch_me_nao_assume_email_de_outra_conta(client, dono, intruso):
    """Trocar o próprio e-mail para o de outra conta seria takeover por colisão."""
    resp = await client.patch(
        "/api/v1/auth/me", json={"email": dono.email}, headers=auth_headers(intruso)
    )
    assert resp.status_code == 409


# ── Convite ──────────────────────────────────────────────────────────────

async def test_convite_aberto_nao_assume_conta_existente(client, db, dono, admin):
    """
    Convite sem e-mail pré-vinculado não pode dar acesso a uma conta que já
    existe — senão qualquer portador do token vira o dono informando o e-mail.
    A guarda vive em `auth_service.accept_invite`.
    """
    gerado = await client.post(
        "/api/v1/auth/invite/generate", json={}, headers=auth_headers(admin)
    )
    assert gerado.status_code == 200
    token = gerado.json()["token"]

    resp = await client.post(
        "/api/v1/auth/invite/accept", json={"token": token, "email": dono.email}
    )

    assert resp.status_code == 400
    assert "access_token" not in resp.json()


async def test_convite_invalido_e_recusado(client):
    resp = await client.post(
        "/api/v1/auth/invite/accept",
        json={"token": str(uuid.uuid4()), "email": "alguem@example.com"},
    )
    assert resp.status_code == 400
