"""
Reconciliação da especialidade a partir dos grupos `[CFM]` da Curseduca.

Roda dentro do LOGIN por embed, a cada login. É o que faz a base antiga — quem
entrou quando `get_or_create_embed_user` criava usuário só com e-mail — ganhar
especialidade sozinha, sem tela e sem uma requisição a mais: o payload do membro
já era baixado para validar a matrícula e tinha os grupos descartados.

O invariante mais importante daqui é o de que NADA nesta rotina pode barrar o
login. Enriquecer perfil é acessório; autenticar não é.
"""

import pytest

from app.medicina import identidade
from app.services import auth_service


def _membro(*grupos: str) -> dict:
    return {"email": "medico@x.com", "groups": [{"name": g} for g in grupos]}


class DbFake:
    """Só o que a rotina usa. Registra se houve commit/rollback."""

    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class UserFake:
    id = "11111111-1111-1111-1111-111111111111"

    def __init__(self, **kw):
        self.specialty = kw.get("specialty")
        self.specialty_slug = kw.get("specialty_slug")
        self.specialties = kw.get("specialties")
        self.specialty_source = kw.get("specialty_source")
        self.specialty_rqe = kw.get("specialty_rqe")
        self.specialty_updated_at = None


@pytest.mark.asyncio
async def test_preenche_especialidade_de_quem_nao_tinha():
    """O caso que motivou tudo: usuário criado pelo embed só com e-mail."""
    db, user = DbFake(), UserFake()

    mudou = await auth_service.reconciliar_especialidade_do_embed(
        db, user, _membro("Turma 2026", "[CFM] CARDIOLOGIA")
    )

    assert mudou is True
    assert user.specialty_slug == "cardiologia"
    assert user.specialty == "Cardiologia"
    assert user.specialty_source == identidade.FONTE_WAID_GRUPO
    assert db.commits == 1


@pytest.mark.asyncio
async def test_duas_residencias_entram_as_duas():
    db, user = DbFake(), UserFake()

    await auth_service.reconciliar_especialidade_do_embed(
        db, user, _membro("[CFM] CLÍNICA MÉDICA", "[CFM] CARDIOLOGIA")
    )

    assert set(user.specialties) == {"cardiologia", "clinica-medica"}
    assert user.specialty_slug == "cardiologia"  # pré-requisito não vence


@pytest.mark.asyncio
async def test_nao_desfaz_o_que_veio_do_cadastro():
    """O grupo pode ser renomeado no painel; o webhook é o registro real.

    Sem esta ordem, um rename de grupo reescreveria a especialidade de todo
    mundo naquele grupo no login seguinte.
    """
    db = DbFake()
    user = UserFake(
        specialty_slug="nefrologia",
        specialty="Nefrologia",
        specialty_source=identidade.FONTE_CADASTRO,
    )

    mudou = await auth_service.reconciliar_especialidade_do_embed(
        db, user, _membro("[CFM] CARDIOLOGIA")
    )

    assert mudou is False
    assert user.specialty_slug == "nefrologia"
    assert db.commits == 0  # nem toca no banco


@pytest.mark.asyncio
async def test_relogar_nao_gera_escrita():
    """Idempotência: sem isto, todo login viraria um UPDATE."""
    db, user = DbFake(), UserFake()
    membro = _membro("[CFM] CARDIOLOGIA")

    assert await auth_service.reconciliar_especialidade_do_embed(db, user, membro)
    assert not await auth_service.reconciliar_especialidade_do_embed(db, user, membro)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_grupo_nao_reconhecido_alerta_e_nao_grava(caplog):
    """Área de atuação do CFM (Hepatologia) vira grupo, mas não é especialidade.

    Tem que sair no log — é o insumo para virar alias. Sem isso o médico fica
    sem especialidade e ninguém descobre.
    """
    db, user = DbFake(), UserFake()

    with caplog.at_level("WARNING"):
        mudou = await auth_service.reconciliar_especialidade_do_embed(
            db, user, _membro("[CFM] Hepatologia")
        )

    assert mudou is False
    assert user.specialty_slug is None
    assert "Hepatologia" in caplog.text


@pytest.mark.asyncio
async def test_reconhecido_convive_com_desconhecido(caplog):
    db, user = DbFake(), UserFake()

    with caplog.at_level("WARNING"):
        await auth_service.reconciliar_especialidade_do_embed(
            db, user, _membro("[CFM] Hepatologia", "[CFM] CARDIOLOGIA")
        )

    assert user.specialty_slug == "cardiologia"
    assert "Hepatologia" in caplog.text


@pytest.mark.asyncio
async def test_generalista_nao_vira_falso_alerta(caplog):
    """`[CFM] GENERALISTA` é o que o cadastro cria quando o CFM não tem nada.

    Usa o MESMO prefixo das especialidades, então sem tratamento explícito ele
    cairia em `desconhecidos` e dispararia "provável área de atuação" para todo
    generalista da base — alerta errado, em volume.
    """
    db, user = DbFake(), UserFake()

    with caplog.at_level("WARNING"):
        mudou = await auth_service.reconciliar_especialidade_do_embed(
            db, user, _membro("[CFM] GENERALISTA")
        )

    assert mudou is False
    assert user.specialty_slug is None  # a verdade: ele não tem especialidade
    assert "área de atuação" not in caplog.text


@pytest.mark.asyncio
async def test_generalista_nao_e_tratado_como_convencao_desconhecida(caplog):
    """Ter `[CFM] GENERALISTA` é informação: o CFM foi consultado e veio vazio.

    Diferente de não ter grupo `[CFM]` nenhum, que só diz que não sabemos.
    """
    db, user = DbFake(), UserFake()

    with caplog.at_level("INFO"):
        await auth_service.reconciliar_especialidade_do_embed(
            db, user, _membro("Turma 2026", "[CFM] GENERALISTA")
        )

    assert "Grupos vistos" not in caplog.text


@pytest.mark.asyncio
async def test_grupos_sem_cfm_sao_registrados_para_descoberta(caplog):
    """Quando não há `[CFM]` nenhum, os nomes vistos viram log.

    É como se descobre a convenção real do cadastro em produção, sem codar
    contra um palpite.
    """
    db, user = DbFake(), UserFake()

    with caplog.at_level("INFO"):
        await auth_service.reconciliar_especialidade_do_embed(
            db, user, _membro("Turma 2026", "Assinantes")
        )

    assert "Assinantes" in caplog.text


@pytest.mark.asyncio
async def test_quem_ja_tem_especialidade_nao_polui_o_log(caplog):
    """A condição precisa se auto-limitar, ou vira ruído permanente."""
    db = DbFake()
    user = UserFake(
        specialty_slug="cardiologia", specialty_source=identidade.FONTE_CADASTRO
    )

    with caplog.at_level("INFO"):
        await auth_service.reconciliar_especialidade_do_embed(db, user, _membro("Turma"))

    assert "Grupos vistos" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "membro",
    [None, {}, {"groups": None}, {"groups": "x"}, {"groups": [{"n": 1}]}, _membro("Turma")],
)
async def test_payload_sem_grupo_util_e_no_op(membro):
    db, user = DbFake(), UserFake()
    assert await auth_service.reconciliar_especialidade_do_embed(db, user, membro) is False
    assert db.commits == 0


@pytest.mark.asyncio
async def test_falha_interna_nunca_derruba_o_login(monkeypatch):
    """O invariante: isto roda dentro do login.

    Se `aplicar_especialidade` explodir por qualquer motivo, o médico entra —
    sem especialidade, que é o estado em que ele já estava.
    """
    db, user = DbFake(), UserFake()

    def explode(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(identidade, "aplicar_especialidade", explode)

    assert await auth_service.reconciliar_especialidade_do_embed(
        db, user, _membro("[CFM] CARDIOLOGIA")
    ) is False
    assert db.rollbacks == 1
