"""
Renomear conversa (PATCH /conversations/{id}), pedido de 2026-09-24.

Não existia: nem rota, nem botão. Os "renomear" da interface eram das pastas. O
que este arquivo trava:

- só o DONO renomeia, e conversa de outro responde 404 (não confirma que o id
  existe) — a mesma regra da leitura;
- renomear NÃO mexe em `updated_at`: a coluna tem `onupdate`, e sem o cuidado a
  conversa renomeada pulava para o topo de "Hoje";
- título vazio ou só com espaços é recusado, e espaços nas pontas somem.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models.models import Conversation
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def dono(user_factory):
    return await user_factory(email="dono@example.com")


async def _renomear(client, conv, usuario, titulo):
    return await client.patch(
        f"/api/v1/conversations/{conv.id}", json={"title": titulo}, headers=auth_headers(usuario)
    )


async def test_o_dono_renomeia_e_a_lista_mostra_o_titulo_novo(client, dono, conversation_factory):
    conv = await conversation_factory(dono, title="Dose de amoxicilina")

    resp = await _renomear(client, conv, dono, "Otite — Maria, 6 anos")

    assert resp.status_code == 200
    assert resp.json()["title"] == "Otite — Maria, 6 anos"
    lista = await client.get("/api/v1/conversations", headers=auth_headers(dono))
    assert [c["title"] for c in lista.json()] == ["Otite — Maria, 6 anos"]


async def test_renomear_nao_muda_a_ordem_do_historico(client, db, dono, conversation_factory):
    antiga = await conversation_factory(dono, title="Antiga")
    recente = await conversation_factory(dono, title="Recente")
    ontem = datetime.now(UTC) - timedelta(days=1)
    await db.execute(update(Conversation).where(Conversation.id == antiga.id).values(updated_at=ontem))
    await db.commit()

    resp = await _renomear(client, antiga, dono, "Antiga, renomeada")

    assert resp.status_code == 200
    assert datetime.fromisoformat(resp.json()["updated_at"]) == ontem, (
        "renomear atualizou updated_at — a conversa pularia para o topo de Hoje"
    )
    lista = await client.get("/api/v1/conversations", headers=auth_headers(dono))
    assert [c["id"] for c in lista.json()] == [str(recente.id), str(antiga.id)]


async def test_conversa_de_outro_medico_responde_404_e_nao_muda(
    client, db, dono, user_factory, conversation_factory
):
    intruso = await user_factory(email="intruso@example.com")
    conv = await conversation_factory(dono, title="Caso do dono")

    resp = await _renomear(client, conv, intruso, "Invadido")

    assert resp.status_code == 404
    await db.refresh(conv)
    assert conv.title == "Caso do dono"


async def test_conversa_apagada_responde_404(client, db, dono, conversation_factory):
    conv = await conversation_factory(dono)
    conv.status = False
    await db.commit()

    assert (await _renomear(client, conv, dono, "Novo")).status_code == 404


@pytest.mark.parametrize("titulo", ["", "   ", "x" * 121], ids=["vazio", "so-espacos", "longo-demais"])
async def test_titulo_invalido_e_recusado(client, dono, conversation_factory, titulo):
    conv = await conversation_factory(dono)

    assert (await _renomear(client, conv, dono, titulo)).status_code == 422


async def test_espacos_extras_somem(client, dono, conversation_factory):
    conv = await conversation_factory(dono)

    resp = await _renomear(client, conv, dono, "  Sepse   no   idoso  ")

    assert resp.json()["title"] == "Sepse no idoso"
