"""
Cópia diária dos membros da Waid com acesso ao Médico 360 (`membros_waid`).

O que fica travado aqui:
- só entram grupos `[CFM]` e `[Cursos Active]`; força de vendas não é baixada;
- uma linha por pessoa, com todos os grupos e o canal certo;
- quem some da Waid perde o acesso, mas a linha fica;
- busca que não acha grupo nenhum é ERRO, não "todo mundo saiu".
"""

import pytest
from sqlalchemy import select

from app.models.models import AuditLog, MembroWaid
from app.services import membros_waid_service as svc
from app.services.integracoes import curseduca_service

GRUPOS = [
    {"id": 120, "name": "[Cursos Active] Médico(a) - ACLS"},
    {"id": 7, "name": "[CFM] CARDIOLOGIA"},
    {"id": 99, "name": "Pfizer | Força de Vendas CFM"},
]
MEMBROS = {
    120: [
        {"id": 369, "uuid": "u-mayara", "name": "Mayara", "email": "mayara@example.com",
         "enteredAt": "2026-10-13T10:17:42.000Z", "hasAccess": True},
        {"id": 400, "uuid": "u-ambos", "name": "Ana", "email": "ana@example.com",
         "enteredAt": "2026-09-01T00:00:00.000Z", "hasAccess": True},
        {"id": 401, "uuid": "u-vencido", "name": "Velho", "email": "velho@example.com",
         "enteredAt": "2025-01-01T00:00:00.000Z", "hasAccess": False},
    ],
    7: [
        {"id": 400, "uuid": "u-ambos", "name": "Ana", "email": "ana@example.com",
         "enteredAt": "2026-08-01T00:00:00.000Z", "hasAccess": True},
    ],
    99: [
        {"id": 500, "uuid": "u-vendas", "name": "Vendedor", "email": "v@example.com",
         "enteredAt": "2026-01-01T00:00:00.000Z", "hasAccess": True},
    ],
}


@pytest.fixture
def waid(monkeypatch):
    pedidos: list = []

    async def listar_grupos(busca):
        return [g for g in GRUPOS if busca.casefold() in g["name"].casefold()]

    async def listar_membros_do_grupo(grupo_id):
        pedidos.append(grupo_id)
        return MEMBROS[grupo_id]

    monkeypatch.setattr(curseduca_service, "listar_grupos", listar_grupos)
    monkeypatch.setattr(curseduca_service, "listar_membros_do_grupo", listar_membros_do_grupo)
    return pedidos


class TestColetar:
    async def test_so_baixa_os_grupos_que_contam(self, waid):
        await svc.coletar()
        assert sorted(waid) == [7, 120]

    async def test_uma_entrada_por_pessoa_com_todos_os_grupos(self, waid):
        membros = await svc.coletar()

        assert set(membros) == {"u-mayara", "u-ambos"}
        assert membros["u-ambos"]["grupos"] == {"[CFM] CARDIOLOGIA", "[Cursos Active] Médico(a) - ACLS"}
        # A entrada mais antiga entre os grupos.
        assert membros["u-ambos"]["entrou_em"].isoformat().startswith("2026-08-01")

    async def test_vinculo_vencido_nao_conta(self, waid):
        assert "u-vencido" not in await svc.coletar()

    async def test_sem_grupo_nenhum_e_erro(self, monkeypatch):
        async def nada(busca):
            return []

        monkeypatch.setattr(curseduca_service, "listar_grupos", nada)
        with pytest.raises(svc.NenhumGrupoEncontrado):
            await svc.coletar()


class TestSincronizar:
    async def _linhas(self, db) -> dict[str, MembroWaid]:
        return {m.waid_uuid: m for m in await db.scalars(select(MembroWaid))}

    async def test_grava_canal_e_profissao(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        linhas = await self._linhas(db)

        assert linhas["u-mayara"].canal_entrada == "cursos_active"
        assert linhas["u-mayara"].profissao == "medico"
        assert linhas["u-mayara"].tem_acesso is True
        assert linhas["u-ambos"].grupos == ["[CFM] CARDIOLOGIA", "[Cursos Active] Médico(a) - ACLS"]

    async def test_quem_sai_perde_acesso_e_a_linha_fica(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        MEMBROS[120] = [m for m in MEMBROS[120] if m["uuid"] != "u-mayara"]
        try:
            resultado = await svc.sincronizar(db, await svc.coletar())
        finally:
            MEMBROS[120].insert(0, {
                "id": 369, "uuid": "u-mayara", "name": "Mayara", "email": "mayara@example.com",
                "enteredAt": "2026-10-13T10:17:42.000Z", "hasAccess": True,
            })
        db.expire_all()
        linhas = await self._linhas(db)

        assert linhas["u-mayara"].tem_acesso is False
        assert linhas["u-ambos"].tem_acesso is True
        assert resultado == {"com_acesso": 1, "perderam_acesso": 1}

    async def test_rodar_duas_vezes_da_o_mesmo(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        await svc.sincronizar(db, await svc.coletar())
        assert len(await self._linhas(db)) == 2

    async def test_deixa_rastro_em_audit_logs(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        [log] = list(await db.scalars(
            select(AuditLog).where(AuditLog.action == svc.ACAO_SINCRONIZACAO)
        ))
        assert log.metadata_ == {"com_acesso": 2, "perderam_acesso": 0}
