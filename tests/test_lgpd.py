"""
Direitos do titular e retenção (item 3.3 do plano de prontidão).

A exclusão de conta já existia. Aqui entram os dois que faltavam:
portabilidade (art. 18, V) e expurgo por prazo (art. 16).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.models import FileExtraction, Interaction, InteractionResponse
from app.services.data_subject_service import (
    RETENCAO_ARQUIVO_DIAS,
    RETENCAO_IMAGEM_DIAS,
    exportar_dados,
    expurgar_dados_vencidos,
)
from tests.conftest import auth_headers


def _dias_atras(dias: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=dias)


@pytest.fixture
async def com_historico(db, user, conversation_factory):
    conv = await conversation_factory(user, title="Caso de dor torácica")
    interacao = Interaction(
        conversation_id=conv.id,
        user_id=user.id,
        feature="ORQUESTRADOR",
        prompt_text="Conduta para dor torácica em paciente hipertenso?",
        started_at=datetime.now(UTC),
    )
    db.add(interacao)
    await db.flush()
    db.add(InteractionResponse(
        interaction_id=interacao.id,
        model_used="claude-sonnet-4-6",
        response_text="Estratificar risco com escore HEART.",
    ))
    await db.flush()
    return conv


# ── Portabilidade ────────────────────────────────────────────────────────

async def test_exportacao_traz_o_historico(db, user, com_historico):
    dados = await exportar_dados(db, user)

    assert dados["titular"]["email"] == user.email
    assert len(dados["conversas"]) == 1
    conversa = dados["conversas"][0]
    assert conversa["titulo"] == "Caso de dor torácica"
    assert "dor torácica" in conversa["interacoes"][0]["pergunta"]
    assert "HEART" in conversa["interacoes"][0]["respostas"][0]["texto"]


async def test_exportacao_nao_traz_dado_de_outro_titular(
    db, user, user_factory, conversation_factory, com_historico
):
    outro = await user_factory(email="outro@example.com")
    await conversation_factory(outro, title="Conversa do outro médico")

    dados = await exportar_dados(db, user)

    import json

    assert "Conversa do outro médico" not in json.dumps(dados, ensure_ascii=False)


async def test_exportacao_omite_imagem_mas_avisa_que_existe(db, user):
    db.add(FileExtraction(
        user_id=user.id, file_name="exame.jpg", file_type="image",
        extracted_text="Hemoglobina 13,2", image_base64="AAAA" * 500,
    ))
    await db.flush()

    dados = await exportar_dados(db, user)

    arquivo = dados["arquivos_enviados"][0]
    assert arquivo["texto_extraido"] == "Hemoglobina 13,2"
    assert arquivo["tem_imagem_armazenada"] is True
    assert "AAAA" not in str(dados), "O base64 tornaria o JSON inutilizável"


async def test_endpoint_de_exportacao(client, user, com_historico):
    resp = await client.get("/api/v1/auth/me/export", headers=auth_headers(user))

    assert resp.status_code == 200
    assert resp.json()["titular"]["email"] == user.email


async def test_exportacao_exige_autenticacao(client):
    assert (await client.get("/api/v1/auth/me/export")).status_code == 401


# ── Retenção ─────────────────────────────────────────────────────────────

async def test_imagem_vencida_e_apagada_mas_o_texto_fica(db, user):
    """
    A imagem crua é o dado mais sensível (foto de exame ou receita, fora do
    alcance do DLP). O texto extraído ainda serve ao histórico.
    """
    extracao = FileExtraction(
        user_id=user.id, file_name="receita.jpg", file_type="image",
        extracted_text="Losartana 50mg", image_base64="dados-da-imagem",
        image_media_type="image/jpeg",
    )
    db.add(extracao)
    await db.flush()
    extracao.created_at = _dias_atras(RETENCAO_IMAGEM_DIAS + 1)
    await db.flush()

    contagem = await expurgar_dados_vencidos(db)

    await db.refresh(extracao)
    assert contagem["imagens_apagadas"] == 1
    assert extracao.image_base64 is None
    assert extracao.image_media_type is None
    assert extracao.extracted_text == "Losartana 50mg"


async def test_imagem_recente_e_preservada(db, user):
    extracao = FileExtraction(
        user_id=user.id, file_name="hoje.jpg", file_type="image",
        extracted_text="x", image_base64="ainda-vale",
    )
    db.add(extracao)
    await db.flush()

    await expurgar_dados_vencidos(db)

    await db.refresh(extracao)
    assert extracao.image_base64 == "ainda-vale"


async def test_arquivo_vencido_e_removido_por_completo(db, user):
    antigo = FileExtraction(user_id=user.id, file_name="antigo.pdf", file_type="pdf", extracted_text="x")
    db.add(antigo)
    await db.flush()
    antigo.created_at = _dias_atras(RETENCAO_ARQUIVO_DIAS + 1)
    await db.flush()

    contagem = await expurgar_dados_vencidos(db)

    assert contagem["arquivos_apagados"] == 1
    restantes = (await db.execute(select(FileExtraction))).scalars().all()
    assert restantes == []


async def test_expurgo_e_idempotente(db, user):
    """Rodar duas vezes não pode dar erro nem apagar o que ainda vale."""
    db.add(FileExtraction(user_id=user.id, file_name="a.pdf", file_type="pdf", extracted_text="x"))
    await db.flush()

    primeira = await expurgar_dados_vencidos(db)
    segunda = await expurgar_dados_vencidos(db)

    assert primeira == segunda == {"imagens_apagadas": 0, "arquivos_apagados": 0, "cache_apagado": 0}
    assert len((await db.execute(select(FileExtraction))).scalars().all()) == 1
