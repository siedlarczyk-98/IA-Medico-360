"""
A tabela de modelos e preços tem fonte de verdade no repositório.

Nenhuma migration povoa `model_pricing`, e os preços viviam só no banco de
produção: um banco restaurado do schema respondia "Modelo não disponível" em
todos os modos. `scripts/seed_models.py` + `scripts/dados/model_pricing.json`
fecham isso, e o teste abaixo impede que um modelo novo entre no código sem
entrar no seed.
"""

import json
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.models import ModelPricing
from app.services.orquestrador_modes import FALLBACK_MODELS, MODE_MODEL_MAP
from scripts import seed_models

# Modelos que o código usa e cujo preço AINDA não foi exportado de produção para o
# JSON. O preço não existe em lugar nenhum do repositório, e inventá-lo seria pior
# que a lacuna: custo errado fura o teto semanal em silêncio. Esvaziar esta lista
# é a pendência — cada modelo sai daqui quando entrar no JSON (o segundo teste
# cobra isso).
PRECO_PENDENTE_DE_EXPORTACAO = {
    "claude-sonnet-5",
    "gemini-2.5-flash",
    "gpt-4o",
    "gpt-5.4-nano",
    "sabia-4-thinking",
    "sonar-pro",
}

MODELO = {
    "model_id": "modelo-de-teste", "provider": "Teste", "provider_type": "anthropic",
    "display_name": "Modelo de Teste", "input_per_million": "3.00",
    "output_per_million": "15.00", "status": True,
}


def _usados_pelo_codigo() -> set[str]:
    usados = {m for m in MODE_MODEL_MAP.values() if m}
    usados |= {m for cadeia in FALLBACK_MODELS.values() for m in cadeia}
    return usados - {"pharmadb"}


def _no_seed() -> set[str]:
    return {m["model_id"] for m in seed_models.carregar()}


def test_todo_modelo_usado_pelo_codigo_esta_no_seed():
    faltando = _usados_pelo_codigo() - _no_seed() - PRECO_PENDENTE_DE_EXPORTACAO

    assert not faltando, (
        f"Modelo usado em MODE_MODEL_MAP/FALLBACK_MODELS e ausente de "
        f"scripts/dados/model_pricing.json: {sorted(faltando)}. Sem preço cadastrado o "
        "modo responde 'Modelo não disponível' num banco novo."
    )


def test_pendencia_resolvida_sai_da_lista():
    ja_exportados = PRECO_PENDENTE_DE_EXPORTACAO & _no_seed()

    assert not ja_exportados, (
        f"{sorted(ja_exportados)} já está no JSON — tire de PRECO_PENDENTE_DE_EXPORTACAO."
    )


def test_a_lista_de_pendentes_nao_esconde_modelo_que_ninguem_usa():
    sobrando = PRECO_PENDENTE_DE_EXPORTACAO - _usados_pelo_codigo()

    assert not sobrando, f"pendente que o código nem usa mais: {sorted(sobrando)}"


def _arquivo(tmp_path, modelos):
    arquivo = tmp_path / "model_pricing.json"
    arquivo.write_text(json.dumps(modelos), encoding="utf-8")
    return arquivo


def test_preco_vira_decimal_a_partir_de_texto(tmp_path):
    modelos = seed_models.carregar(_arquivo(tmp_path, [{**MODELO, "input_per_million": "0.075"}]))

    assert modelos[0]["input_per_million"] == Decimal("0.075")


def test_seed_com_modelo_repetido_e_recusado(tmp_path):
    with pytest.raises(ValueError, match="repetido"):
        seed_models.carregar(_arquivo(tmp_path, [MODELO, MODELO]))


def test_seed_com_campo_faltando_e_recusado(tmp_path):
    incompleto = {k: v for k, v in MODELO.items() if k != "output_per_million"}

    with pytest.raises(ValueError, match="output_per_million"):
        seed_models.carregar(_arquivo(tmp_path, [incompleto]))


async def test_aplicar_e_idempotente(db, tmp_path):
    modelos = seed_models.carregar(_arquivo(tmp_path, [MODELO]))

    primeira = await seed_models.aplicar(db, modelos)
    segunda = await seed_models.aplicar(db, modelos)

    assert primeira["criados"] == ["modelo-de-teste"]
    assert segunda == {"criados": [], "atualizados": [], "fora_do_seed": []}
    assert await db.scalar(select(func.count()).select_from(ModelPricing)) == 1


async def test_preco_divergente_e_corrigido(db, tmp_path, model_pricing_factory):
    await model_pricing_factory(model_id="modelo-de-teste", input_per_million="1.00")
    modelos = seed_models.carregar(_arquivo(tmp_path, [MODELO]))

    relatorio = await seed_models.aplicar(db, modelos)

    assert relatorio["atualizados"] and "input_per_million" in relatorio["atualizados"][0]
    gravado = (await db.execute(select(ModelPricing))).scalar_one()
    assert gravado.input_per_million == Decimal("3.00")


async def test_conferir_nao_grava(db, tmp_path):
    modelos = seed_models.carregar(_arquivo(tmp_path, [MODELO]))

    relatorio = await seed_models.aplicar(db, modelos, gravar=False)

    assert relatorio["criados"] == ["modelo-de-teste"]
    assert await db.scalar(select(func.count()).select_from(ModelPricing)) == 0


async def test_modelo_fora_do_seed_e_avisado_e_nunca_apagado(db, tmp_path, model_pricing_factory):
    await model_pricing_factory(model_id="modelo-antigo-em-uso")
    modelos = seed_models.carregar(_arquivo(tmp_path, [MODELO]))

    relatorio = await seed_models.aplicar(db, modelos)

    assert relatorio["fora_do_seed"] == ["modelo-antigo-em-uso"]
    assert await db.scalar(select(func.count()).select_from(ModelPricing)) == 2
