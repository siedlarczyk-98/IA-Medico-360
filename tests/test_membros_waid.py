"""
Cópia diária dos membros da Waid que contam como usuários do Médico 360 (`membros_waid`).

O que fica travado aqui:
- só os grupos `[Cursos Active]`, `[CFM]` e `[ONBOARDING]` viram linha;
- quem também está num andar de farmacêutica é "Usuário Immerso";
- grupo vazio não é consultado (a rodada de 2026-10-13 caiu num deles);
- quem some da Waid perde o acesso, mas a linha fica;
- relatório sem grupo que conta é ERRO, não "todo mundo saiu";
- o canal chega à conta do app, inclusive à criada por login direto.
"""

import copy

import pytest
from sqlalchemy import select

from app.models.models import AuditLog, MembroWaid
from app.services import membros_waid_service as svc
from app.services.integracoes import curseduca_service

PFIZER = {"uuid": "60f3263a-f1a7-4cc8-b8d8-3e48597d1b1e", "name": "Pfizer"}
MEDICO360 = {"uuid": "4037b710-50c5-11ed-b97b-16058182e383", "name": "Médico 360"}

RELATORIO = [
    {"id": 120, "name": "[Cursos Active] Médico(a) - ACLS", "membersCount": 2, "tenants": [MEDICO360]},
    {"id": 47, "name": "[CFM] CARDIOLOGIA", "membersCount": 2, "tenants": [MEDICO360]},
    {"id": 116, "name": "[ONBOARDING] - Estudante", "membersCount": 1, "tenants": []},
    {"id": 64, "name": "[CFM] ALERGIA E IMUNOLOGIA", "membersCount": 0, "tenants": [MEDICO360]},
    {"id": 35, "name": "[Pfizer] ST-ATTRs - Médico", "membersCount": 2, "tenants": [PFIZER]},
    {"id": 2, "name": "Interno Immerso/Paciente360", "membersCount": 1, "tenants": [MEDICO360]},
]


def _m(uuid, email, entrada="2026-10-13T10:00:00.000Z", acesso=True):
    return {"id": abs(hash(uuid)) % 10_000, "uuid": uuid, "name": uuid, "email": email,
            "enteredAt": entrada, "hasAccess": acesso}


MEMBROS = {
    120: [_m("u-mayara", "mayara@example.com"), _m("u-ambos", "ana@example.com", "2026-09-01T00:00:00Z")],
    47: [_m("u-ambos", "ana@example.com", "2026-08-01T00:00:00Z"), _m("u-pfizer", "dr@example.com"),
         _m("u-vencido", "velho@example.com", acesso=False)],
    116: [_m("u-estudante", "est@example.com")],
    35: [_m("u-pfizer", "dr@example.com"), _m("u-so-pfizer", "rep@example.com")],
    2: [_m("u-interno", "equipe@example.com")],
}


@pytest.fixture
def waid(monkeypatch):
    membros = copy.deepcopy(MEMBROS)
    pedidos: list = []

    async def relatorio():
        return RELATORIO

    async def listar_membros_do_grupo(grupo_id):
        pedidos.append(grupo_id)
        return membros[grupo_id]

    monkeypatch.setattr(curseduca_service, "listar_relatorio_de_grupos", relatorio)
    monkeypatch.setattr(curseduca_service, "listar_membros_do_grupo", listar_membros_do_grupo)
    return membros, pedidos


class TestColetar:
    async def test_consulta_so_o_que_precisa(self, waid):
        _, pedidos = waid
        await svc.coletar()
        # Os três que contam + o andar de farmacêutica. Nem o vazio (64), nem o
        # grupo interno que não conta (2).
        assert sorted(pedidos) == [35, 47, 116, 120]

    async def test_uma_entrada_por_pessoa_com_todos_os_grupos(self, waid):
        membros = await svc.coletar()

        assert set(membros) == {"u-mayara", "u-ambos", "u-pfizer", "u-estudante"}
        assert membros["u-ambos"]["grupos"] == {"[CFM] CARDIOLOGIA", "[Cursos Active] Médico(a) - ACLS"}
        assert membros["u-ambos"]["entrou_em"].isoformat().startswith("2026-08-01")

    async def test_quem_so_esta_no_andar_de_farmaceutica_nao_entra(self, waid):
        assert "u-so-pfizer" not in await svc.coletar()

    async def test_marca_quem_esta_em_andar_de_farmaceutica(self, waid):
        membros = await svc.coletar()
        assert membros["u-pfizer"]["em_andar_de_farmaceutica"] is True
        assert membros["u-estudante"]["em_andar_de_farmaceutica"] is False

    async def test_vinculo_vencido_nao_conta(self, waid):
        assert "u-vencido" not in await svc.coletar()

    async def test_sem_grupo_que_conta_e_erro(self, monkeypatch):
        async def so_farmaceutica():
            return [g for g in RELATORIO if g["id"] == 35]

        monkeypatch.setattr(curseduca_service, "listar_relatorio_de_grupos", so_farmaceutica)
        with pytest.raises(svc.NenhumGrupoEncontrado):
            await svc.coletar()


class TestSincronizar:
    async def _linhas(self, db) -> dict[str, MembroWaid]:
        return {m.waid_uuid: m for m in await db.scalars(select(MembroWaid))}

    async def test_grava_o_canal_de_cada_porta(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        linhas = await self._linhas(db)

        assert linhas["u-mayara"].canal_entrada == "cursos_active"
        assert linhas["u-ambos"].canal_entrada == "cursos_active"
        assert linhas["u-pfizer"].canal_entrada == "immerso"
        assert linhas["u-estudante"].canal_entrada == "lp_medico360"
        assert linhas["u-estudante"].profissao == "estudante_medicina"

    async def test_quem_sai_perde_acesso_e_a_linha_fica(self, db, waid):
        membros, _ = waid
        await svc.sincronizar(db, await svc.coletar())
        membros[120] = [m for m in membros[120] if m["uuid"] != "u-mayara"]

        resultado = await svc.sincronizar(db, await svc.coletar())
        db.expire_all()
        linhas = await self._linhas(db)

        assert linhas["u-mayara"].tem_acesso is False
        assert linhas["u-ambos"].tem_acesso is True
        assert resultado["perderam_acesso"] == 1

    async def test_rodar_duas_vezes_da_o_mesmo(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        await svc.sincronizar(db, await svc.coletar())
        assert len(await self._linhas(db)) == 4

    async def test_canal_chega_a_conta_do_app(self, db, waid, user_factory):
        pela_waid = await user_factory(email="outro@example.com")
        pela_waid.waid_uuid = "u-mayara"
        login_direto = await user_factory(email="ANA@example.com")  # sem waid_uuid
        sem_grupo = await user_factory(email="ninguem@example.com")
        await db.commit()

        resultado = await svc.sincronizar(db, await svc.coletar())
        for u in (pela_waid, login_direto, sem_grupo):
            await db.refresh(u)

        assert pela_waid.canal_entrada == "cursos_active"
        assert login_direto.canal_entrada == "cursos_active"
        assert sem_grupo.canal_entrada is None
        assert resultado["contas_com_canal_atualizado"] == 2

    async def test_deixa_rastro_em_audit_logs(self, db, waid):
        await svc.sincronizar(db, await svc.coletar())
        [log] = list(await db.scalars(
            select(AuditLog).where(AuditLog.action == svc.ACAO_SINCRONIZACAO)
        ))
        assert log.metadata_["com_acesso"] == 4
