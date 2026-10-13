"""
A PREVENT deixa rastro de USO, e só de uso.

Ela não grava execução (nada do paciente fica no banco). Desde 2026-10-13 grava
em `audit_logs` quem usou e quando, para contar no painel da diretoria. O que
fica travado aqui é que esse rastro não carrega nenhum dado clínico.
"""

import json

from sqlalchemy import select

from app.calculators.routers.prevent_router import ACAO_USO
from app.models.calculators import CalculatorExecution
from app.models.models import AuditLog

PACIENTE = {
    "sexo": "F", "idade": 57, "ct_mgdl": 213.0, "hdl_mgdl": 47.0, "sbp_mmhg": 141.0,
    "bmi": 31.7, "egfr": 73.0, "diabetes": True, "fumante": False,
    "antihtn_use": True, "statin_use": False,
}


async def _registros(db):
    return list(await db.scalars(select(AuditLog).where(AuditLog.action == ACAO_USO)))


async def test_calculo_registra_quem_usou(as_user, db, user):
    resp = await as_user.post("/api/v1/prevent/calculate", json=PACIENTE)

    assert resp.status_code == 200
    [registro] = await _registros(db)
    assert registro.user_id == user.id


async def test_registro_nao_carrega_dado_do_paciente(as_user, db):
    await as_user.post("/api/v1/prevent/calculate", json=PACIENTE)

    [registro] = await _registros(db)
    conteudo = json.dumps({
        "metadata": registro.metadata_, "entity_id": str(registro.entity_id),
        "entity_type": registro.entity_type,
    })
    for valor in ("213", "141", "31.7", "73", "57"):
        assert valor not in conteudo, valor
    assert not registro.metadata_


async def test_continua_sem_gravar_execucao(as_user, db):
    await as_user.post("/api/v1/prevent/calculate", json=PACIENTE)

    assert list(await db.scalars(select(CalculatorExecution))) == []


async def test_requisicao_invalida_nao_registra(as_user, db):
    resp = await as_user.post("/api/v1/prevent/calculate", json={**PACIENTE, "sexo": "X"})

    assert resp.status_code == 422
    assert await _registros(db) == []
