"""
`interno.atividade` (migration 021): o que cada pessoa fez, com o texto da pergunta.

O que fica travado:
- um evento por linha, de cada tipo, com quem e quando;
- o role do Metabase NÃO lê a view: texto clínico não pode chegar ao LLM do MCP.
"""

import importlib.util
import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models.models import AuditLog, Interaction

_VERSIONS = Path(__file__).parent.parent / "alembic" / "versions"


def _carregar(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, _VERSIONS / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


m016 = _carregar("migration_016", "016_schema_gerencial.py")
m021 = _carregar("migration_021", "021_interno_atividade.py")


@pytest_asyncio.fixture
async def interno(db_conn):
    # O role do Metabase precisa existir para o teste de isolamento.
    for sql in [*m016.comandos_upgrade(), *m021.comandos_upgrade()]:
        await db_conn.exec_driver_sql(sql)


async def _linhas(conn) -> list[dict]:
    res = await conn.execute(text(
        f"SELECT row_to_json(v)::text FROM {m021.SCHEMA}.{m021.VIEW} v ORDER BY quando"
    ))
    return [json.loads(linha[0]) for linha in res]


@pytest.mark.usefixtures("interno")
class TestAtividade:
    async def test_pergunta_vem_com_texto_quem_e_quando(self, db, db_conn, user_factory, conversation_factory):
        medico = await user_factory(name="Dra. Ana", email="ana@example.com")
        conversa = await conversation_factory(medico)
        db.add(Interaction(
            conversation_id=conversa.id, user_id=medico.id, feature="ORQUESTRADOR",
            mode="QUICK_SEARCH", prompt_text="Dose de amoxicilina em criança de 20 kg?",
        ))
        await db.commit()

        [linha] = await _linhas(db_conn)
        assert linha["tipo"] == "pergunta"
        assert linha["detalhe"] == "Dose de amoxicilina em criança de 20 kg?"
        assert (linha["nome"], linha["email"]) == ("Dra. Ana", "ana@example.com")
        assert linha["modo"] == "QUICK_SEARCH"
        assert linha["quando"] is not None and linha["dia"] is not None

    async def test_prevent_entrada_e_cada_tipo_tem_sua_linha(self, db, db_conn, user_factory):
        medico = await user_factory()
        db.add_all([
            AuditLog(user_id=medico.id, action="prevent.calculo", entity_type="calculadora"),
            AuditLog(user_id=medico.id, action="auth.embed", metadata_={"via": "token"}),
            AuditLog(user_id=medico.id, action="outra.coisa"),
        ])
        await db.commit()

        tipos = sorted((linha["tipo"], linha["detalhe"]) for linha in await _linhas(db_conn))
        assert tipos == [("calculadora", "PREVENT"), ("entrada_waid", None)]

    async def test_role_do_metabase_nao_le(self, db_conn):
        sp = await db_conn.begin_nested()
        try:
            await db_conn.exec_driver_sql(f"SET LOCAL ROLE {m016.ROLE}")
            with pytest.raises(DBAPIError, match="permission denied"):
                await db_conn.exec_driver_sql(f"SELECT 1 FROM {m021.SCHEMA}.{m021.VIEW} LIMIT 1")
        finally:
            await sp.rollback()

    async def test_downgrade_remove(self, db_conn):
        for sql in m021.comandos_downgrade():
            await db_conn.exec_driver_sql(sql)
        res = await db_conn.exec_driver_sql(f"SELECT to_regclass('{m021.SCHEMA}.{m021.VIEW}')")
        assert res.scalar() is None
