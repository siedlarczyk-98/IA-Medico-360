"""
Harness de teste do Médico 360.

Este arquivo é importado pelo pytest ANTES de qualquer módulo de teste — e é por
isso que a trava de banco abaixo funciona: quando a aplicação for importada, ela
já vai ler a URL do banco de teste, nunca a do `.env`.

Rodar localmente:

    docker run -d --name m360-test-db -p 55433:5432 \
        -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=medico360_test pgvector/pgvector:pg16
    pytest

A imagem precisa ser a `pgvector`: a migration 001 cria um índice `ivfflat`.
SQLite não serve — os modelos usam JSONB e UUID do dialeto PostgreSQL.
"""

import os
import uuid
import warnings
from decimal import Decimal

# ─────────────────────────────────────────────────────────────────────────────
# TRAVA DE BANCO — precisa vir antes de importar qualquer coisa de `app`
# ─────────────────────────────────────────────────────────────────────────────
# O `.env` do projeto aponta para o banco hospedado. Sem esta trava, um `pytest`
# distraído roda migrations e apaga tabelas em produção. A URL de teste é sempre
# explícita, e nunca herdada do ambiente de execução normal.

DEFAULT_TEST_DB = "postgresql+asyncpg://test:test@localhost:55433/medico360_test"
TEST_DATABASE_URL = os.environ.get("DATABASE_URL_TEST", DEFAULT_TEST_DB)

_nome_banco = TEST_DATABASE_URL.rsplit("/", 1)[-1].split("?")[0]
if "test" not in _nome_banco.lower():
    raise RuntimeError(
        f"Recusando rodar testes contra o banco '{_nome_banco}': o nome precisa "
        "conter 'test'. Ajuste DATABASE_URL_TEST."
    )

# A partir daqui, todo `get_settings()` enxerga o banco de teste.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET_KEY", "chave-de-teste-nao-usar-em-producao-com-32-bytes-ou-mais")
os.environ.setdefault("APP_ENV", "development")

# Redis de teste numa porta FECHADA, por atribuição e não `setdefault`. A app
# trata toda falha de Redis como silenciosa, então um Redis local ligado na 6379
# mudava o comportamento da suíte sem ninguém perceber: cache de triagem
# respondendo, rate limit por e-mail contando entre testes. Na máquina de um
# passava, na do outro não. Porta fechada dá o mesmo resultado em todo lugar.
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/15"

# Chaves de provedores: FALSAS, também por atribuição. O `.env` do projeto tem as
# chaves reais, e o pydantic-settings as carregava na suíte — a `PUBMED_API_KEY`
# de produção apareceu na URL de uma chamada que a guarda de rede bloqueou. A
# guarda segura a chamada, mas a chave não tem por que estar na memória do teste.
# A exceção é o E2E deliberado, que precisa delas (ver `test_e2e_pergunta_real`).
if os.environ.get("E2E_REDE_REAL") != "1":
    for _chave in (
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_AI_API_KEY",
        "PERPLEXITY_API_KEY", "MARITACA_API_KEY", "PHARMADB_API_KEY",
        "PUBMED_API_KEY", "SENDGRID_API_KEY", "CURSEDUCA_API_KEY",
        "CURSEDUCA_ACCESS_TOKEN", "INTERCOM_IDENTITY_SECRET", "PHOENIX_API_KEY",
        "SENTRY_DSN",
    ):
        os.environ[_chave] = "" if _chave in ("PHOENIX_API_KEY", "SENTRY_DSN") else "chave-falsa-de-teste"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.models.models import Conversation, Folder, ModelPricing, User
from app.services import auth_service

# Confere que a trava pegou: se o cache do settings foi populado antes daqui,
# o teste rodaria contra o banco errado sem avisar.
assert get_settings().database_url == TEST_DATABASE_URL, (
    "app.core.config foi importado antes da trava do conftest — "
    "verifique se algum plugin do pytest importa `app` antes."
)


_schema_criado = False


@pytest_asyncio.fixture
async def engine():
    """
    Engine por teste, com o schema criado uma única vez na primeira chamada.

    O engine é por teste de propósito: um engine de escopo de sessão guarda
    conexões presas ao event loop da sessão, e o pytest-asyncio dá um loop novo
    a cada teste — o que produz `Future attached to a different loop`. Criar o
    engine é barato; o caro é o DDL, e esse roda só uma vez.
    """
    global _schema_criado

    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    if not _schema_criado:
        async with eng.begin() as conn:
            # O cache semântico usa pgvector; parte dos modelos vive no schema
            # `calculators`. `create_all` não cria nem extensão nem schema.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            for schema in sorted({t.schema for t in Base.metadata.tables.values() if t.schema}):
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

            # `create_all` em vez de `alembic upgrade head`: aqui o schema vem dos
            # models, que é o que os testes exercitam, e recriá-lo é muito mais
            # rápido que aplicar a cadeia inteira. A cadeia tem verificação própria
            # no CI (job `migrations`), separando os dois tipos de falha.
            #
            # Diferença conhecida: os índices `semantic_cache_embedding_hnsw_idx`
            # (HNSW, ver migration 003) e `semantic_cache_mode_expires_idx` existem
            # em produção mas não estão declarados nos models, então não são criados
            # aqui. Nenhum teste depende deles — mas quem for testar performance do
            # cache semântico precisa saber.
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _schema_criado = True

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_conn(engine):
    """
    Conexão do teste, presa numa transação que sofre rollback no fim.

    Exposta separadamente porque alguns serviços (o streaming do Orquestrador)
    abrem a própria sessão via `session_factory` em vez de receber `get_db`.
    Para testá-los sem escapar do isolamento, monta-se uma factory sobre esta
    mesma conexão — ver `tests/test_orquestrador_stream.py`.
    """
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            yield conn
        finally:
            await trans.rollback()


def fabrica_sobre(db_conn) -> async_sessionmaker:
    """
    A ÚNICA forma de montar sessão sobre a conexão do teste.

    `join_transaction_mode="create_savepoint"` é o ponto. O padrão do SQLAlchemy
    para uma conexão que já está em transação é `rollback_only`: o `commit()` da
    sessão não faz nada, mas o `rollback()` reverte a transação EXTERNA — a do
    harness. Todo caminho da app que chama `db.rollback()` (recuperação de
    erro no stream, no `/query`, no digest, no cache semântico) apagava os
    dados que o próprio teste tinha preparado, e por isso esses caminhos eram
    intestáveis. Com savepoint, `commit()` e `rollback()` da sessão agem só
    sobre o savepoint dela, e o rollback final de `db_conn` continua limpando
    tudo.

    Existiam 18 cópias de `async_sessionmaker(bind=db_conn, ...)` espalhadas
    pelos testes. Uma só, para que esta decisão valha em todas.
    """
    return async_sessionmaker(
        bind=db_conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
def fabrica_de_sessao(db_conn) -> async_sessionmaker:
    """Para serviços que abrem a própria sessão via `async_session_factory`."""
    return fabrica_sobre(db_conn)


async def truncar_tudo(engine) -> None:
    """TRUNCATE de todas as tabelas — a limpeza de `fabrica_com_conexoes_reais`."""
    tabelas = ", ".join(
        f'"{t.schema}"."{t.name}"' if t.schema else f'"{t.name}"'
        for t in Base.metadata.sorted_tables
    )

    async with engine.begin() as conn:
        # O TRUNCATE pede trava exclusiva em TODAS as tabelas e, sem limite,
        # espera para sempre por quem segura qualquer uma delas. O job de
        # backend do CI pendurou 6 h em cinco runs de set/2026, todos parados
        # no mesmo ponto (~52% da suíte, onde está o primeiro uso deste
        # TRUNCATE). A causa mais provável: uma conexão esquecida "idle in
        # transaction" por um teste anterior (tarefa de fundo que morreu com
        # o event loop do teste no meio de uma transação), segurando trava que
        # nunca soltaria. Localmente não reproduz — depende de tempo.
        #
        # Entre testes (a suíte é serial) nenhuma transação legítima fica
        # aberta, então quem está parado em transação é vazamento: encerra, e
        # AVISA quem era — o aviso aparece no resumo do pytest e aponta a
        # origem para corrigir de vez. E o `lock_timeout` troca qualquer
        # espera restante por um erro claro em segundos, nunca mais horas.
        presas = (await conn.execute(text(
            "SELECT pid, left(regexp_replace(query, '\\s+', ' ', 'g'), 160), "
            "       now() - state_change "
            "  FROM pg_stat_activity "
            " WHERE datname = current_database() AND pid <> pg_backend_pid() "
            "   AND state LIKE 'idle in transaction%'"
        ))).all()
        for pid, _consulta, _idade in presas:
            await conn.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        if presas:
            warnings.warn(
                "fabrica_com_conexoes_reais: encerradas conexões presas em transação "
                "antes do TRUNCATE (vazamento de algum teste anterior): "
                + "; ".join(f"pid {p} parado há {i}: {q}" for p, q, i in presas),
                stacklevel=1,
            )
        await conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        await conn.execute(text(f"TRUNCATE {tabelas} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def fabrica_com_conexoes_reais(engine):
    """
    Fábrica de sessão sobre um pool REAL de duas conexões, com commit de verdade.

    OPCIONAL, e cara — só para o que o harness normal não consegue exprimir:
    bloqueio entre transações, esgotamento de pool, corrida entre sessões. Em
    `db_conn` tudo divide UMA conexão, então duas sessões nunca disputam linha
    nem conexão, e um teste de concorrência ali passa sem provar nada.

    O preço é o isolamento: aqui o commit é real, então a limpeza é por
    TRUNCATE de todas as tabelas no fim. Não misture com `db`/`client` no mesmo
    teste — a transação aberta de `db_conn` não enxerga o que for comitado aqui
    e ainda pode segurar bloqueio contra o TRUNCATE.

    `pool_size=2, max_overflow=0, pool_timeout=2`: o teste de esgotamento de
    pool falha em 2s em vez de pendurar a suíte.
    """
    # Antes TAMBÉM: aqui o commit é real, então uma execução anterior morta no
    # meio (Ctrl+C, processo encerrado) deixa linhas que o rollback do harness
    # normal nunca alcança — e elas contaminariam a suíte inteira.
    await truncar_tudo(engine)
    eng = create_async_engine(
        TEST_DATABASE_URL, pool_size=2, max_overflow=0, pool_timeout=2
    )
    try:
        yield async_sessionmaker(bind=eng, expire_on_commit=False)
    finally:
        await eng.dispose()
        await truncar_tudo(engine)


@pytest_asyncio.fixture
async def db(db_conn) -> AsyncSession:
    """
    Sessão por teste. Nada do que o teste escreve sobrevive: a conexão está
    numa transação externa revertida em `db_conn`.
    """
    session = fabrica_sobre(db_conn)()
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def client(db) -> AsyncClient:
    """Cliente HTTP contra a app real — exercita middleware, CORS e rate limit."""
    async def _get_db_override():
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_factory(db):
    """Cria usuários persistidos. `role='admin'` para os testes de rota restrita."""
    async def _create(
        email: str | None = None,
        role: str = "beta_user",
        status: bool = True,
        onboarding_complete: bool = True,
        name: str | None = "Usuário de Teste",
    ) -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:12]}@example.com",
            role=role,
            status=status,
            onboarding_complete=onboarding_complete,
            name=name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    return _create


@pytest_asyncio.fixture
async def user(user_factory) -> User:
    return await user_factory()


@pytest_asyncio.fixture
async def folder_factory(db):
    """Pasta pertencente a um usuário — base dos testes de isolamento."""
    async def _create(
        dono: User, name: str = "Pasta", clinical_context: str | None = None
    ) -> Folder:
        folder = Folder(user_id=dono.id, name=name, clinical_context=clinical_context)
        db.add(folder)
        await db.commit()
        await db.refresh(folder)
        return folder

    return _create


@pytest_asyncio.fixture
async def conversation_factory(db):
    """Conversa pertencente a um usuário, opcionalmente dentro de uma pasta."""
    async def _create(
        dono: User,
        title: str = "Consulta de teste",
        feature: str = "ORQUESTRADOR",
        folder: Folder | None = None,
    ) -> Conversation:
        conv = Conversation(
            user_id=dono.id,
            title=title,
            feature=feature,
            status=True,
            folder_id=folder.id if folder else None,
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        return conv

    return _create


@pytest_asyncio.fixture
async def model_pricing_factory(db):
    """
    Registra um modelo na tabela de preços.

    Limpa o cache de `pricing.py` antes e depois: ele é um TTLCache de módulo
    (1h) e, sem isso, o preço de um teste vazaria para os seguintes.
    """
    from app.services import pricing

    pricing._pricing_cache.clear()

    async def _create(
        model_id: str = "modelo-teste",
        provider_type: str = "anthropic",
        input_per_million: str = "3.00",
        output_per_million: str = "15.00",
        status: bool = True,
    ) -> ModelPricing:
        mp = ModelPricing(
            model_id=model_id,
            provider=provider_type,
            provider_type=provider_type,
            display_name=model_id,
            input_per_million=Decimal(input_per_million),
            output_per_million=Decimal(output_per_million),
            status=status,
        )
        db.add(mp)
        await db.commit()
        pricing._pricing_cache.clear()
        return mp

    yield _create
    pricing._pricing_cache.clear()


@pytest_asyncio.fixture
async def calculator_factory(db):
    """
    Calculadora completa e executável: especialidade + definição + campos + versão.

    Usa a fórmula real `cockcroft_gault_v1` (a de menos campos) para que
    `/execute` percorra o motor de verdade, não um mock.
    """
    from app.calculators import cache as catalogo_cache
    from app.models.calculators import (
        CalculatorDefinition,
        CalculatorField,
        CalculatorStatusEnum,
        CalculatorVersion,
        EngineTypeEnum,
        Specialty,
    )

    # O catálogo é cacheado in-process por 300s. Sem limpar, a calculadora criada
    # aqui fica invisível para o endpoint (e o catálogo vaza entre testes).
    catalogo_cache.clear()

    async def _create(slug: str = "cockcroft-gault", formula_key: str = "cockcroft_gault_v1"):
        sufixo = uuid.uuid4().hex[:6]
        especialidade = Specialty(name=f"Nefrologia {sufixo}", slug=f"nefrologia-{sufixo}")
        db.add(especialidade)
        await db.flush()

        calc = CalculatorDefinition(
            specialty_id=especialidade.id,
            slug=slug,
            name="Clearance de Creatinina (Cockcroft-Gault)",
            description="Estimativa de função renal.",
            engine_type=EngineTypeEnum.FORMULA.value,
            status=CalculatorStatusEnum.ACTIVE.value,
        )
        db.add(calc)
        await db.flush()

        campos = [
            ("idade", "Idade", "NUMBER", "anos"),
            ("peso_kg", "Peso", "NUMBER", "kg"),
            ("altura_cm", "Altura", "NUMBER", "cm"),
            ("creatinina_mgdl", "Creatinina", "NUMBER", "mg/dL"),
            ("sexo", "Sexo", "SELECT", None),
            ("tipo_peso", "Tipo de peso", "SELECT", None),
        ]
        opcoes = {
            "sexo": [{"value": "M", "label": "Masculino"}, {"value": "F", "label": "Feminino"}],
            "tipo_peso": [
                {"value": "real", "label": "Real"},
                {"value": "ideal", "label": "Ideal"},
                {"value": "ajustado", "label": "Ajustado"},
            ],
        }
        for ordem, (chave, rotulo, tipo, unidade) in enumerate(campos):
            db.add(CalculatorField(
                calculator_id=calc.id, key=chave, label=rotulo, field_type=tipo,
                unit=unidade, required=True, display_order=ordem,
                options=opcoes.get(chave),
            ))

        db.add(CalculatorVersion(
            calculator_id=calc.id, version_number=1,
            formula_key=formula_key, is_active=True,
            clinical_reference="Cockcroft & Gault, 1976",
        ))
        await db.commit()
        await db.refresh(calc)
        catalogo_cache.clear()
        return calc

    yield _create
    catalogo_cache.clear()


INPUTS_COCKCROFT_VALIDOS = {
    "idade": 65,
    "peso_kg": 70,
    "altura_cm": 170,
    "creatinina_mgdl": 1.2,
    "sexo": "M",
    "tipo_peso": "real",
}


def auth_headers(user: User) -> dict[str, str]:
    """Header Authorization para um usuário — mesmo caminho de emissão da app."""
    return {"Authorization": f"Bearer {auth_service.create_access_token(user)}"}


@pytest.fixture
def as_user(client, user):
    """Cliente já autenticado como um usuário comum."""
    client.headers.update(auth_headers(user))
    return client


@pytest_asyncio.fixture
async def admin(user_factory) -> User:
    return await user_factory(role="admin")


# ─────────────────────────────────────────────────────────────────────────────
# Guarda de rede
# ─────────────────────────────────────────────────────────────────────────────
# Nenhum teste pode tocar Anthropic, OpenAI, PharmaDB, PubMed, Curseduca ou
# SendGrid. Um teste que vaze para a rede é lento, instável e gasta cota real —
# além de poder mandar dado de teste para um serviço de verdade.
#
# A guarda tem DUAS camadas, e a segunda existe porque a primeira não basta:
#
#  1. `VazamentoDeRede` herda de `BaseException`, não de `Exception`. A app está
#     cheia de `except Exception` em volta de chamada de modelo — é o caminho de
#     contingência, e é legítimo. Mas ele transformava a violação da guarda em
#     "provedor falhou", e o teste passava exercitando o fallback em vez do
#     caminho principal que o nome dele promete. Eram 23 testes assim.
#
#  2. Ainda assim alguém pode escrever `except BaseException` (ou o
#     `asyncio.gather` de um TaskGroup pode empacotar a exceção). Por isso toda
#     tentativa também é REGISTRADA, e o registro é conferido no encerramento do
#     teste. Engolir a exceção não salva mais ninguém: o teste reprova no fim.

class VazamentoDeRede(BaseException):
    """
    Chamada HTTP externa durante um teste.

    Herda de `BaseException` de propósito, para atravessar os `except Exception`
    do código sob teste. Não capture isto.
    """


@pytest.fixture(autouse=True)
def bloqueia_rede_externa(request, monkeypatch):
    """Falha o teste se ele tentar sair para a rede. Use a marca `rede_real` para optar por fora."""
    if request.node.get_closest_marker("rede_real"):
        # `yield` e não `return`: fixture generator precisa produzir um valor em
        # todos os caminhos, senão o pytest levanta "did not yield a value".
        yield
        return

    tentativas: list[str] = []

    async def _proibido(self, requisicao, *args, **kwargs):
        alvo = f"{requisicao.method} {requisicao.url}"
        tentativas.append(alvo)
        raise VazamentoDeRede(
            f"Teste tentou fazer uma chamada HTTP externa: {alvo}. Use um fake do "
            "provider ou marque o teste com @pytest.mark.rede_real se a chamada "
            "for intencional."
        )

    # Bloqueia o TRANSPORTE de rede, não o `AsyncClient`: o cliente de teste também
    # é um AsyncClient, só que sobre ASGITransport (em processo). Patchar a classe
    # inteira derrubaria os próprios testes de integração.
    monkeypatch.setattr(
        "httpx.AsyncHTTPTransport.handle_async_request", _proibido, raising=False
    )

    yield tentativas

    if tentativas:
        distintas = sorted(set(tentativas))
        raise AssertionError(
            f"O teste passou, mas tentou {len(tentativas)} chamada(s) HTTP externa(s) "
            "e alguém engoliu o erro da guarda — provavelmente um `except Exception` "
            "em volta da chamada de modelo. O que o teste exercitou foi o caminho de "
            "contingência, não o principal.\nAlvos: " + ", ".join(distintas)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Estado de processo que vaza entre testes
# ─────────────────────────────────────────────────────────────────────────────
# Disjuntores e rate limiter são objetos de MÓDULO: o rollback do banco não os
# alcança. Um teste que provoca falhas de integração deixava o contador do
# disjuntor a uma falha de abrir para os 170 testes seguintes, e um teste que
# martela uma rota gastava a cota por IP dos próximos — falha que só aparecia
# conforme a ordem de execução.

#
# O terceiro é o POOL DO ENGINE GLOBAL da app (`app.core.database.engine`). O
# pytest-asyncio dá um event loop novo a cada teste, e uma conexão asyncpg só
# funciona no loop em que nasceu. Quem usa o engine global sem override — o
# `_checa_postgres` do health check, as tarefas de background — podia receber do
# pool uma conexão do loop de um teste anterior. Às vezes o SQLAlchemy conseguia
# descartá-la (o aviso `Connection._cancel was never awaited`), às vezes virava
# erro: `test_readiness_ok_com_tudo_no_ar` falhava em ~2 de cada 7 rodadas.
# `dispose(close=False)` troca o pool por um vazio sem tentar fechar, no loop
# errado, conexões que já não podem ser fechadas.

@pytest.fixture(autouse=True)
def estado_de_processo_limpo():
    from app.core import circuit_breaker
    from app.core.database import engine as engine_da_app
    from app.core.limiter import limiter

    circuit_breaker.reset_todos()
    limiter.reset()
    engine_da_app.sync_engine.dispose(close=False)
    yield
    circuit_breaker.reset_todos()
    limiter.reset()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "rede_real: permite que o teste faça chamadas HTTP externas de verdade"
    )
