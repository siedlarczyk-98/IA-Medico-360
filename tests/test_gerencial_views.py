"""
Schema `gerencial` — o que o Metabase da diretoria enxerga.

As propriedades travadas aqui são de privacidade, não de formato:
- nenhum texto clínico ou dado pessoal escrito no app aparece em view alguma;
- o role do Metabase lê as views e NÃO lê as tabelas do app;
- contas `admin` e `test` (a equipe testando) ficam fora dos números;
- a única exceção é `usuarios_lista` (018): nome e e-mail, e nada além disso;
- `acesso` (018) conta quem tem acesso pela Waid, abriu a IA e usou a IA.

O banco de teste é montado por `create_all`, sem migrations; o schema é criado
aqui com o mesmo SQL das migrations 016, 017 e 018, dentro da transação do teste
(a tabela `membros_waid` e as colunas novas de `users` vêm do `create_all`).
"""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.landing_pages import LandingPage, Submission
from app.models.models import (
    AuditLog,
    FileExtraction,
    Interaction,
    InteractionResponse,
    MembroWaid,
    PharmaAlert,
)

_VERSIONS = Path(__file__).parent.parent / "alembic" / "versions"


def _carregar(nome_modulo: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome_modulo, _VERSIONS / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


migration = _carregar("migration_016", "016_schema_gerencial.py")
migration_017 = _carregar("migration_017", "017_gerencial_sem_contas_teste.py")
migration_018 = _carregar("migration_018", "018_canal_e_acesso.py")
LISTA = migration_018.VIEW_LISTA
ACESSO = migration_018.VIEW_ACESSO

# Marca escrita em todo campo livre e pessoal. Se aparecer em qualquer view,
# alguma coluna vazou.
SEGREDO = "SEGREDO-CLINICO-7f3a"


@pytest_asyncio.fixture
async def gerencial(db_conn):
    for sql in [
        *migration.comandos_upgrade(),
        *migration_017.comandos_upgrade(),
        *migration_018.comandos_upgrade(),
    ]:
        await db_conn.exec_driver_sql(sql)


@pytest_asyncio.fixture
async def dados(db, user_factory, conversation_factory):
    """Um médico com uma pergunta completa, anexo, alerta, login e lead."""
    medico = await user_factory(
        email=f"{SEGREDO.lower()}@example.com", name=f"Dr. {SEGREDO}"
    )
    medico.phone_number = "11999990000"
    medico.crm = "123456"
    conversa = await conversation_factory(medico, title=f"Paciente {SEGREDO}")

    pergunta = Interaction(
        conversation_id=conversa.id,
        user_id=medico.id,
        feature="ORQUESTRADOR",
        mode="BIZU",
        prompt_text=f"Gestante com {SEGREDO}",
        topic_detected=f"tema {SEGREDO}",
        status="completed",
    )
    db.add(pergunta)
    await db.flush()
    db.add_all([
        InteractionResponse(
            interaction_id=pergunta.id,
            model_used="modelo-x",
            response_text=f"Resposta sobre {SEGREDO}",
            error_message=f"falhou em {SEGREDO}",
        ),
        FileExtraction(
            user_id=medico.id,
            interaction_id=pergunta.id,
            file_name=f"{SEGREDO}.pdf",
            file_type="pdf",
            extracted_text=f"Laudo {SEGREDO}",
        ),
        PharmaAlert(
            interaction_id=pergunta.id,
            alert_level=3,
            alert_color="vermelho",
            description=f"Interação {SEGREDO}",
            source_api="pharmadb",
            doctor_justification=f"Justificativa {SEGREDO}",
        ),
        AuditLog(
            user_id=medico.id,
            action="auth.embed",
            metadata_={"via": "token", "origin": f"https://{SEGREDO}.example.com"},
            ip_address="203.0.113.42",
            user_agent=f"Navegador {SEGREDO}",
        ),
    ])
    lp = LandingPage(slug="contabil", name="Contábil")
    db.add(lp)
    await db.flush()
    db.add(Submission(
        landing_page_id=lp.id,
        user_id=medico.id,
        name=f"Lead {SEGREDO}",
        email=f"lead-{SEGREDO.lower()}@example.com",
        phone="11988887777",
    ))
    await db.commit()
    return medico


async def _linhas(conn, view: str) -> list[dict]:
    res = await conn.execute(text(f"SELECT row_to_json(v)::text FROM gerencial.{view} v"))
    return [json.loads(linha[0]) for linha in res]


@pytest.mark.usefixtures("gerencial")
class TestNadaSensivelSai:
    async def test_nenhuma_view_carrega_texto_livre_nem_dado_pessoal(self, db_conn, dados):
        vazou = {}
        for view in [*migration.VIEWS, ACESSO]:
            conteudo = json.dumps(await _linhas(db_conn, view), ensure_ascii=False)
            for marca in (SEGREDO, SEGREDO.lower(), "203.0.113.42", "11999990000",
                          "11988887777", "123456", str(dados.id)):
                if marca in conteudo:
                    vazou.setdefault(view, []).append(marca)

        assert vazou == {}

    async def test_as_views_nao_ficam_vazias_de_proposito(self, db_conn, dados):
        # Sem isto o teste acima passaria com views que não devolvem nada.
        for view in ("usuarios", "perguntas", "respostas_modelo", "acessos", "captacao"):
            assert await _linhas(db_conn, view), view

    async def test_usuario_ref_e_o_mesmo_em_todas_as_views(self, db_conn, dados):
        refs = {
            view: {linha["usuario_ref"] for linha in await _linhas(db_conn, view)}
            for view in ("usuarios", "perguntas", "acessos")
        }
        assert refs["usuarios"] == refs["perguntas"] == refs["acessos"]

    async def test_pergunta_marca_anexo_e_alerta(self, db_conn, dados):
        [pergunta] = await _linhas(db_conn, "perguntas")
        assert pergunta["com_anexo"] is True
        assert pergunta["com_alerta_farmaco"] is True


@pytest.mark.usefixtures("gerencial")
class TestAdminFicaFora:
    async def test_pergunta_de_admin_nao_conta(self, db, db_conn, admin, conversation_factory):
        conversa = await conversation_factory(admin)
        db.add(Interaction(
            conversation_id=conversa.id, user_id=admin.id,
            feature="ORQUESTRADOR", prompt_text="teste da equipe",
        ))
        await db.commit()

        assert await _linhas(db_conn, "perguntas") == []
        assert await _linhas(db_conn, "usuarios") == []


@pytest.mark.usefixtures("gerencial")
class TestContaDeTesteFicaFora:
    """Conta marcada com `role = 'test'` some de tudo — custo e captação inclusive."""

    VIEWS_POR_USUARIO = ("usuarios", "perguntas", "respostas_modelo", "acessos", "captacao")

    async def _marcar_como_teste(self, db, medico):
        medico.role = "test"
        await db.commit()

    async def test_some_de_todas_as_views_por_usuario(self, db, db_conn, dados):
        await self._marcar_como_teste(db, dados)

        for view in self.VIEWS_POR_USUARIO:
            assert await _linhas(db_conn, view) == [], view

    async def test_conta_normal_ao_lado_continua_contando(
        self, db, db_conn, dados, user_factory, conversation_factory
    ):
        medico = await user_factory()
        conversa = await conversation_factory(medico)
        db.add(Interaction(
            conversation_id=conversa.id, user_id=medico.id,
            feature="ORQUESTRADOR", prompt_text="pergunta real",
        ))
        await self._marcar_como_teste(db, dados)

        assert len(await _linhas(db_conn, "usuarios")) == 1
        assert len(await _linhas(db_conn, "perguntas")) == 1

    async def test_lead_sem_conta_continua_contando(self, db, db_conn):
        lp = LandingPage(slug="parceiros", name="Parceiros")
        db.add(lp)
        await db.flush()
        db.add(Submission(landing_page_id=lp.id, name="Lead", email="lead@example.com"))
        await db.commit()

        [lead] = await _linhas(db_conn, "captacao")
        assert lead["virou_usuario"] is False

    async def test_downgrade_volta_a_contar(self, db, db_conn, dados):
        await self._marcar_como_teste(db, dados)
        # Na ordem do alembic: a 018 sai antes da 017.
        for sql in [*migration_018.comandos_downgrade(), *migration_017.comandos_downgrade()]:
            await db_conn.exec_driver_sql(sql)

        assert len(await _linhas(db_conn, "perguntas")) == 1


@pytest.mark.usefixtures("gerencial")
class TestListaDeUsuarios:
    """`usuarios_lista` diz quem é quem — e só isso: nada clínico, nada de contato além do e-mail."""

    async def test_traz_nome_e_email(self, db_conn, dados):
        [linha] = await _linhas(db_conn, LISTA)
        assert linha["nome"] == dados.name
        assert linha["email"] == dados.email

    async def test_fora_nome_e_email_nada_sensivel_sai(self, db_conn, dados):
        [linha] = await _linhas(db_conn, LISTA)
        del linha["nome"], linha["email"]
        conteudo = json.dumps(linha, ensure_ascii=False)
        for marca in (SEGREDO, SEGREDO.lower(), "203.0.113.42", "11999990000",
                      "11988887777", "123456", str(dados.id)):
            assert marca not in conteudo, marca

    async def test_conta_uso_e_casa_com_as_outras_views(self, db_conn, dados):
        [linha] = await _linhas(db_conn, LISTA)
        [usuario] = await _linhas(db_conn, "usuarios")
        assert linha["usuario_ref"] == usuario["usuario_ref"]
        assert linha["perguntas"] == 1
        assert linha["calculadoras"] == 0
        assert linha["usou_ia"] is True
        assert linha["situacao"] == "Usou a IA"
        assert linha["ultimo_uso_em"] is not None
        assert linha["ultimo_acesso_waid_em"] is not None

    async def test_conta_sem_uso_aparece_com_zero(self, db_conn, user_factory):
        await user_factory()
        [linha] = await _linhas(db_conn, LISTA)
        assert linha["perguntas"] == 0
        assert linha["usou_ia"] is False
        assert linha["situacao"] == "Abriu a IA, não usou"
        assert linha["ultimo_uso_em"] is None

    async def test_so_entrar_pela_waid_e_acesso_nao_uso(self, db, db_conn, user_factory):
        medico = await user_factory()
        db.add(AuditLog(user_id=medico.id, action="auth.embed", metadata_={"via": "token"}))
        await db.commit()

        [linha] = await _linhas(db_conn, LISTA)
        assert linha["ultimo_acesso_waid_em"] is not None
        assert linha["usou_ia"] is False
        assert linha["ultimo_uso_em"] is None

    async def test_admin_e_teste_ficam_fora(self, db, db_conn, dados, admin):
        dados.role = "test"
        await db.commit()
        assert await _linhas(db_conn, LISTA) == []

    async def test_downgrade_remove_as_views_e_o_perfil(self, db_conn, dados):
        for sql in migration_018.comandos_downgrade():
            await db_conn.exec_driver_sql(sql)
        for view in (LISTA, ACESSO):
            res = await db_conn.exec_driver_sql(f"SELECT to_regclass('gerencial.{view}')")
            assert res.scalar() is None
        [usuario] = await _linhas(db_conn, "usuarios")
        assert "perfil" not in usuario


_CFM = datetime(2026, 9, 1, tzinfo=UTC)


def _membro_waid(uuid: str, *grupos: str, tem_acesso: bool = True, **kw) -> MembroWaid:
    from app.medicina import canal

    return MembroWaid(
        waid_uuid=uuid, grupos=sorted(grupos), tem_acesso=tem_acesso,
        canal_entrada=canal.canal_de_entrada(grupos), profissao=canal.profissao(grupos),
        entrou_em=datetime(2026, 10, 13, tzinfo=UTC), **kw,
    )


@pytest.mark.usefixtures("gerencial")
class TestAcesso:
    """Com acesso > abriu a IA > usou a IA, uma linha por pessoa."""

    async def test_quem_so_tem_acesso_conta_sem_ter_aberto(self, db, db_conn):
        db.add(_membro_waid("u-mayara", "[Cursos Active] Médico(a) - ACLS",
                            nome="Mayara", email="mayara@example.com"))
        await db.commit()

        [linha] = await _linhas(db_conn, ACESSO)
        assert linha["abriu_ia"] is False
        assert linha["usou_ia"] is False
        assert linha["canal_entrada"] == "Cursos Active"
        assert linha["perfil"] == "Médico, estágio não informado"
        assert linha["usuario_ref"] is None

        [nominal] = await _linhas(db_conn, LISTA)
        assert (nominal["nome"], nominal["situacao"]) == ("Mayara", "Só tem acesso")

    async def test_membro_com_conta_e_uma_pessoa_so(self, db, db_conn, dados):
        dados.waid_uuid = "u-dados"
        db.add(_membro_waid("u-dados", "[CFM] CARDIOLOGIA"))
        await db.commit()

        [linha] = await _linhas(db_conn, ACESSO)
        assert linha["abriu_ia"] is True
        assert linha["usou_ia"] is True
        assert linha["em_grupo_medico360"] is True
        assert linha["canal_entrada"] == "Cadastro CFM"
        assert linha["perfil"] == "Especialista"
        [usuario] = await _linhas(db_conn, "usuarios")
        assert linha["usuario_ref"] == usuario["usuario_ref"]

    async def test_conta_sem_grupo_tambem_tem_acesso(self, db, db_conn, user_factory):
        await user_factory()
        [linha] = await _linhas(db_conn, ACESSO)
        assert linha["abriu_ia"] is True
        assert linha["em_grupo_medico360"] is False
        assert linha["canal_entrada"] == "Login direto"

    async def test_quem_perdeu_o_acesso_e_nao_tem_conta_sai(self, db, db_conn):
        db.add(_membro_waid("u-saiu", "[Cursos Active] Médico(a) - ACLS", tem_acesso=False))
        await db.commit()
        assert await _linhas(db_conn, ACESSO) == []

    async def test_conta_de_teste_sai_mesmo_estando_na_waid(self, db, db_conn, dados):
        dados.waid_uuid = "u-dados"
        dados.role = "test"
        db.add(_membro_waid("u-dados", "[CFM] CARDIOLOGIA"))
        await db.commit()
        assert await _linhas(db_conn, ACESSO) == []

    async def test_perfil_do_grupo_sem_conta(self, db, db_conn):
        db.add_all([
            _membro_waid("u-gen", "[CFM] GENERALISTA"),
            _membro_waid("u-esp", "[CFM] PEDIATRIA"),
            _membro_waid("u-enf", "[Cursos Active] Enfermeiro(a) - PALS"),
        ])
        await db.commit()
        perfis = sorted(linha["perfil"] for linha in await _linhas(db_conn, ACESSO))
        assert perfis == ["Enfermagem", "Especialista", "Generalista"]

    async def test_acesso_nao_tem_nome_nem_email(self, db, db_conn):
        db.add(_membro_waid("u-x", "[CFM] PEDIATRIA", nome=f"Dr. {SEGREDO}",
                            email=f"{SEGREDO.lower()}@example.com"))
        await db.commit()
        conteudo = json.dumps(await _linhas(db_conn, ACESSO), ensure_ascii=False)
        assert SEGREDO not in conteudo
        assert SEGREDO.lower() not in conteudo


@pytest.mark.usefixtures("gerencial")
class TestPerfil:
    """Especialista / residente / generalista / estudante: CFM primeiro, declarado depois."""

    @pytest.mark.parametrize(("campos", "perfil", "fonte"), [
        # Grupo `[CFM] <especialidade>`
        ({"specialty_slug": "cardiologia", "specialty_source": "waid_grupo",
          "crm_verified_at": _CFM}, "Especialista", "cfm"),
        # O CFM não separa R1 de especialista; quem declarou residente é residente.
        ({"specialty_slug": "cardiologia", "specialty_source": "waid_grupo",
          "crm_verified_at": _CFM, "med_status": "residente"}, "Residente", "declarado"),
        # `[CFM] GENERALISTA`: só `crm_verified_at`, sem especialidade.
        ({"crm_verified_at": _CFM}, "Generalista", "cfm"),
        ({"crm_verified_at": _CFM, "med_status": "residente"}, "Residente", "declarado"),
        # Grupo `[CFM]` prova CRM: "graduando" declarado perde.
        ({"crm_verified_at": _CFM, "med_status": "graduando"}, "Generalista", "cfm"),
        # Só o declarado.
        ({"med_status": "especialista"}, "Especialista", "declarado"),
        ({"med_status": "generalista"}, "Generalista", "declarado"),
        ({"med_status": "graduando"}, "Estudante", "declarado"),
        # Grupo da Cursos Active.
        ({"profissao": "enfermeiro", "med_status": "especialista"}, "Enfermagem", "cursos_active"),
        ({"profissao": "estudante_enfermagem"}, "Enfermagem", "cursos_active"),
        ({"profissao": "estudante_medicina"}, "Estudante", "cursos_active"),
        # Estudante pelo grupo, mas já com CRM no CFM: formou-se.
        ({"profissao": "estudante_medicina", "crm_verified_at": _CFM}, "Generalista", "cfm"),
        # "Médico(a)" da Cursos Active: o onboarding diz o estágio...
        ({"profissao": "medico", "med_status": "generalista"}, "Generalista", "declarado"),
        # ...e sem onboarding fica médico sem estágio.
        ({"profissao": "medico"}, "Médico, estágio não informado", "cursos_active"),
        ({"profissao": "profissional_saude"}, "Outro profissional de saúde", "cursos_active"),
        # Especialidade digitada pelo médico não é verificação.
        ({"specialty_slug": "cardiologia", "specialty_source": "declarado"},
         "Não informado", None),
        ({}, "Não informado", None),
    ])
    async def test_classifica(self, db, db_conn, user_factory, campos, perfil, fonte):
        medico = await user_factory()
        for campo, valor in campos.items():
            setattr(medico, campo, valor)
        await db.commit()

        for view in ("usuarios", LISTA, ACESSO):
            [linha] = await _linhas(db_conn, view)
            assert (linha["perfil"], linha["perfil_fonte"]) == (perfil, fonte), view


@pytest.mark.usefixtures("gerencial")
class TestRoleDoMetabase:
    """O role lê as views (que rodam com os direitos do dono) e nada além."""

    async def _como_metabase(self, db_conn, sql: str):
        sp = await db_conn.begin_nested()
        try:
            await db_conn.exec_driver_sql(f"SET LOCAL ROLE {migration.ROLE}")
            return (await db_conn.exec_driver_sql(sql)).all()
        finally:
            await sp.rollback()

    async def test_le_as_views(self, db_conn, dados):
        linhas = await self._como_metabase(db_conn, "SELECT count(*) FROM gerencial.perguntas")
        assert linhas[0][0] == 1

    @pytest.mark.parametrize("view", [LISTA, ACESSO])
    async def test_le_as_views_da_018(self, db_conn, dados, view):
        linhas = await self._como_metabase(db_conn, f"SELECT count(*) FROM gerencial.{view}")
        assert linhas[0][0] == 1

    @pytest.mark.parametrize("tabela", [
        "public.users",
        "public.interactions",
        "public.interaction_responses",
        "public.file_extractions",
        "public.audit_logs",
        "calculators.calculator_executions",
        "landing_pages.submissions",
        "public.membros_waid",
    ])
    async def test_nao_le_as_tabelas_do_app(self, db_conn, tabela):
        with pytest.raises(DBAPIError, match="permission denied"):
            await self._como_metabase(db_conn, f"SELECT 1 FROM {tabela} LIMIT 1")
