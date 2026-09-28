"""
Schema `gerencial` — o que o Metabase da diretoria enxerga.

As propriedades travadas aqui são de privacidade, não de formato:
- nenhum texto clínico ou dado pessoal escrito no app aparece em view alguma;
- o role do Metabase lê as views e NÃO lê as tabelas do app;
- contas `admin` e `test` (a equipe testando) ficam fora dos números.

O banco de teste é montado por `create_all`, sem migrations; o schema é criado
aqui com o mesmo SQL das migrations 016 e 017, dentro da transação do teste.
"""

import importlib.util
import json
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

# Marca escrita em todo campo livre e pessoal. Se aparecer em qualquer view,
# alguma coluna vazou.
SEGREDO = "SEGREDO-CLINICO-7f3a"


@pytest_asyncio.fixture
async def gerencial(db_conn):
    for sql in [*migration.comandos_upgrade(), *migration_017.comandos_upgrade()]:
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
        for view in migration.VIEWS:
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
        for sql in migration_017.comandos_downgrade():
            await db_conn.exec_driver_sql(sql)

        assert len(await _linhas(db_conn, "perguntas")) == 1


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

    @pytest.mark.parametrize("tabela", [
        "public.users",
        "public.interactions",
        "public.interaction_responses",
        "public.file_extractions",
        "public.audit_logs",
        "calculators.calculator_executions",
        "landing_pages.submissions",
    ])
    async def test_nao_le_as_tabelas_do_app(self, db_conn, tabela):
        with pytest.raises(DBAPIError, match="permission denied"):
            await self._como_metabase(db_conn, f"SELECT 1 FROM {tabela} LIMIT 1")
