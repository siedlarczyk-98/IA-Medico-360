"""
Páginas de captação: os envios públicos.

Eram 31% de cobertura e ZERO teste — quatro rotas anônimas de escrita. E as listas
de múltipla escolha não tinham teto: uma requisição com 300 mil itens virava 300
mil linhas (item 48 da varredura de 2026-09-18).
"""

import pytest
from sqlalchemy import func, select

from app.models.landing_pages import (
    AccountingPainSelection,
    LandingPage,
    PartnerCategorySelection,
    Submission,
)
from app.schemas.landing_pages import MAX_OPCOES

CONTABILIDADE = {
    "name": "Dra. Lead", "email": "lead@example.com",
    "career_stage": "Especialista", "income_method": "PJ", "accountant_status": "Tenho contador",
    "revenue_range": "20 a 40 mil", "willingness_to_pay": "Até R$ 300",
    "pain_points": ["Pago imposto demais", "Não entendo meu pró-labore"],
}
PARCEIROS = {
    "name": "Dr. Lead", "email": "lead@example.com", "career_stage": "Residente",
    "categories": ["Equipamentos", "Seguros"], "desired_brands": "Littmann",
}
FINANCAS = {
    "name": "Dra. Lead", "email": "lead@example.com",
    "career_stage": "Especialista", "main_pain_point": "Não sei onde investir",
}


@pytest.fixture(autouse=True)
async def catalogo(db):
    """Em produção estas linhas vêm do seed da migration; o harness usa `create_all`."""
    for slug in ("finance", "accounting", "partners", "calculators"):
        db.add(LandingPage(slug=slug, name=slug))
    await db.commit()


async def _contar(db, modelo) -> int:
    return await db.scalar(select(func.count()).select_from(modelo))


# ── Os envios funcionam ──────────────────────────────────────────────────────

@pytest.mark.parametrize(("rota", "corpo"), [
    ("accounting", CONTABILIDADE), ("partners", PARCEIROS), ("finance", FINANCAS),
])
async def test_envio_anonimo_e_gravado(client, db, rota, corpo):
    resp = await client.post(f"/api/v1/landing-pages/{rota}/submit", json=corpo)

    assert resp.status_code == 201, resp.text
    gravado = (await db.execute(select(Submission))).scalar_one()
    assert gravado.email == "lead@example.com"


async def test_cada_opcao_marcada_vira_uma_linha(client, db):
    await client.post("/api/v1/landing-pages/accounting/submit", json=CONTABILIDADE)

    assert await _contar(db, AccountingPainSelection) == 2


async def test_segundo_envio_do_mesmo_email_e_recusado(client, db):
    await client.post("/api/v1/landing-pages/finance/submit", json=FINANCAS)

    repetido = await client.post("/api/v1/landing-pages/finance/submit", json=FINANCAS)

    assert repetido.status_code == 409
    assert await _contar(db, Submission) == 1


async def test_mesmo_email_em_outra_pagina_e_aceito(client):
    await client.post("/api/v1/landing-pages/finance/submit", json=FINANCAS)

    outra = await client.post("/api/v1/landing-pages/partners/submit", json=PARCEIROS)

    assert outra.status_code == 201


async def test_check_responde_so_para_pagina_conhecida(client):
    assert (await client.get("/api/v1/landing-pages/inexistente/check?email=a@b.com")).status_code == 404

    await client.post("/api/v1/landing-pages/finance/submit", json=FINANCAS)
    resp = await client.get("/api/v1/landing-pages/finance/check?email=lead@example.com")
    assert resp.json() == {"already_submitted": True}


# ── Os limites ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("rota", "corpo", "campo", "tabela"), [
    ("accounting", CONTABILIDADE, "pain_points", AccountingPainSelection),
    ("partners", PARCEIROS, "categories", PartnerCategorySelection),
])
async def test_lista_gigante_e_recusada_e_nada_e_gravado(client, db, rota, corpo, campo, tabela):
    abuso = {**corpo, campo: [f"opção {i}" for i in range(5000)]}

    resp = await client.post(f"/api/v1/landing-pages/{rota}/submit", json=abuso)

    assert resp.status_code == 422
    assert await _contar(db, tabela) == 0
    assert await _contar(db, Submission) == 0


async def test_o_teto_cabe_um_formulario_de_verdade(client):
    no_limite = {**CONTABILIDADE, "pain_points": [f"opção {i}" for i in range(MAX_OPCOES)]}

    resp = await client.post("/api/v1/landing-pages/accounting/submit", json=no_limite)

    assert resp.status_code == 201


async def test_opcao_com_texto_enorme_e_recusada(client, db):
    abuso = {**PARCEIROS, "categories": ["x" * 10_000]}

    resp = await client.post("/api/v1/landing-pages/partners/submit", json=abuso)

    assert resp.status_code == 422
    assert await _contar(db, Submission) == 0


async def test_opcao_em_branco_nao_conta_como_escolha(client):
    resp = await client.post(
        "/api/v1/landing-pages/partners/submit", json={**PARCEIROS, "categories": ["   "]}
    )

    assert resp.status_code == 422


async def test_redacao_nova_da_pagina_nao_vira_422(client):
    """O teto é de quantidade e tamanho, NÃO uma lista fechada de opções: mudar a
    frase na página não pode fazer o backend recusar o lead."""
    resp = await client.post(
        "/api/v1/landing-pages/accounting/submit",
        json={**CONTABILIDADE, "pain_points": ["Uma opção que só existe na página nova"]},
    )

    assert resp.status_code == 201
