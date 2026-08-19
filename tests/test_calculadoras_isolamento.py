"""
Isolamento das calculadoras e dos uploads (fecha o item 1.2/1.3).

As rotas de calculadora já eram varridas pelos testes de autenticação, mas os
recursos POR USUÁRIO nunca foram testados: histórico de execuções e favoritos.
Ambos guardam dado clínico — o histórico carrega os inputs do paciente em JSONB.

O upload entra aqui pelo mesmo motivo: `FileExtraction` guarda o texto extraído
(e a imagem em base64), e o `file_id` é consumido depois pelo orquestrador.
"""

import pytest
from sqlalchemy import select

from app.models.calculators import CalculatorExecution, CalculatorFavorite
from app.models.models import FileExtraction
from tests.conftest import INPUTS_COCKCROFT_VALIDOS, auth_headers


@pytest.fixture
async def dono(user_factory):
    return await user_factory(email="dono-calc@example.com")


@pytest.fixture
async def intruso(user_factory):
    return await user_factory(email="intruso-calc@example.com")


async def _executa(client, calc, user, inputs=None):
    return await client.post(
        f"/api/v1/calculators/{calc.slug}/execute",
        json={"inputs": inputs or INPUTS_COCKCROFT_VALIDOS},
        headers=auth_headers(user),
    )


# ── A calculadora roda de verdade ────────────────────────────────────────

async def test_execucao_produz_resultado(client, calculator_factory, dono):
    """Contraprova: sem isto, os testes de isolamento passariam com o motor quebrado."""
    calc = await calculator_factory()

    resp = await _executa(client, calc, dono)

    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    assert corpo["result"], "A fórmula deveria devolver um resultado"


# ── Histórico é por usuário ──────────────────────────────────────────────

async def test_historico_nao_vaza_execucao_alheia(client, calculator_factory, dono, intruso):
    calc = await calculator_factory()
    await _executa(client, calc, dono, {**INPUTS_COCKCROFT_VALIDOS, "idade": 88})

    resp = await client.get(
        f"/api/v1/calculators/{calc.slug}/history", headers=auth_headers(intruso)
    )

    assert resp.status_code == 200
    assert resp.json() == [], "O intruso enxergou execuções de outro médico"


async def test_dono_ve_a_propria_execucao(client, calculator_factory, dono):
    calc = await calculator_factory()
    await _executa(client, calc, dono)

    resp = await client.get(
        f"/api/v1/calculators/{calc.slug}/history", headers=auth_headers(dono)
    )

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_execucao_e_gravada_com_o_dono_correto(client, db, calculator_factory, dono):
    """Os inputs guardados em JSONB são dado clínico — o vínculo precisa estar certo."""
    calc = await calculator_factory()
    await _executa(client, calc, dono)

    execucoes = (await db.execute(select(CalculatorExecution))).scalars().all()
    assert len(execucoes) == 1
    assert execucoes[0].user_id == dono.id


# ── Favoritos são por usuário ────────────────────────────────────────────

async def test_favorito_de_um_nao_aparece_para_outro(client, calculator_factory, dono, intruso):
    calc = await calculator_factory()
    marcou = await client.put(
        f"/api/v1/calculators/{calc.slug}/favorite", headers=auth_headers(dono)
    )
    assert marcou.status_code in (200, 204), marcou.text

    lista_intruso = await client.get("/api/v1/calculators", headers=auth_headers(intruso))
    lista_dono = await client.get("/api/v1/calculators", headers=auth_headers(dono))

    def favoritada(resposta):
        item = next(c for c in resposta.json() if c["slug"] == calc.slug)
        return item.get("is_favorite", item.get("favorite"))

    assert favoritada(lista_dono) is True
    assert favoritada(lista_intruso) is False


async def test_desfavoritar_nao_afeta_o_favorito_alheio(
    client, db, calculator_factory, dono, intruso
):
    calc = await calculator_factory()
    await client.put(f"/api/v1/calculators/{calc.slug}/favorite", headers=auth_headers(dono))

    await client.delete(
        f"/api/v1/calculators/{calc.slug}/favorite", headers=auth_headers(intruso)
    )

    favoritos = (await db.execute(select(CalculatorFavorite))).scalars().all()
    assert [f.user_id for f in favoritos] == [dono.id], "O favorito do dono sumiu"


# ── Calculadora inexistente ──────────────────────────────────────────────

async def test_slug_inexistente_responde_404(client, dono):
    resp = await client.get(
        "/api/v1/calculators/calculadora-que-nao-existe", headers=auth_headers(dono)
    )
    assert resp.status_code == 404


async def test_execucao_com_input_invalido_nao_grava(client, db, calculator_factory, dono):
    """Entrada inválida precisa ser rejeitada antes de virar linha no histórico."""
    calc = await calculator_factory()

    resp = await _executa(
        client, calc, dono, {**INPUTS_COCKCROFT_VALIDOS, "idade": -5, "creatinina_mgdl": "abc"}
    )

    assert resp.status_code in (400, 422), resp.text
    assert (await db.execute(select(CalculatorExecution))).scalars().all() == []


# ── Uploads ──────────────────────────────────────────────────────────────

PDF_MINIMO = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


async def test_upload_e_gravado_com_o_dono_correto(client, db, dono):
    resp = await client.post(
        "/api/v1/uploads/extract",
        files={"file": ("exame.pdf", PDF_MINIMO, "application/pdf")},
        headers=auth_headers(dono),
    )

    assert resp.status_code == 200, resp.text
    extracoes = (await db.execute(select(FileExtraction))).scalars().all()
    assert len(extracoes) == 1
    assert extracoes[0].user_id == dono.id


async def test_upload_rejeita_tipo_nao_suportado(client, dono):
    resp = await client.post(
        "/api/v1/uploads/extract",
        files={"file": ("script.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh")},
        headers=auth_headers(dono),
    )
    assert resp.status_code == 415


async def test_upload_rejeita_conteudo_que_mente_o_tipo(client, dono):
    """Extensão e content-type são do cliente; a assinatura do arquivo é a verdade."""
    resp = await client.post(
        "/api/v1/uploads/extract",
        files={"file": ("falso.pdf", b"MZ\x90\x00isto e um executavel", "application/pdf")},
        headers=auth_headers(dono),
    )
    assert resp.status_code == 415
