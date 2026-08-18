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
os.environ.setdefault("JWT_SECRET_KEY", "chave-de-teste-nao-usar-em-producao")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import Conversation, Folder, User  # noqa: E402
from app.services import auth_service  # noqa: E402

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

            # `create_all` em vez de `alembic upgrade head` — e aqui não há escolha:
            # a cadeia de migrations NÃO aplica num banco vazio. A `001` é a raiz
            # (down_revision=None) e só cria `semantic_cache`; nenhuma migration cria
            # `users`, `conversations` ou `interactions`. Essas tabelas nasceram de um
            # `create_all` fora do Alembic, e as migrations seguintes são ALTERs em
            # cima. Consequência: hoje o banco não pode ser reconstruído do zero, e o
            # schema dos models é a única fonte de verdade completa.
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _schema_criado = True

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    """
    Sessão por teste dentro de uma transação revertida no fim.

    Cada teste enxerga um banco limpo sem pagar o custo de recriar o schema:
    a conexão fica presa numa transação externa que sofre rollback ao final,
    então nada do que o teste escreveu sobrevive.
    """
    async with engine.connect() as conn:
        trans = await conn.begin()
        factory = async_sessionmaker(bind=conn, expire_on_commit=False)
        session = factory()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


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
        await db.flush()
        await db.refresh(user)
        return user

    return _create


@pytest_asyncio.fixture
async def user(user_factory) -> User:
    return await user_factory()


@pytest_asyncio.fixture
async def folder_factory(db):
    """Pasta pertencente a um usuário — base dos testes de isolamento."""
    async def _create(dono: User, name: str = "Pasta") -> Folder:
        folder = Folder(user_id=dono.id, name=name)
        db.add(folder)
        await db.flush()
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
        await db.flush()
        await db.refresh(conv)
        return conv

    return _create


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

@pytest.fixture(autouse=True)
def bloqueia_rede_externa(request, monkeypatch):
    """Falha o teste se ele tentar sair para a rede. Use a marca `rede_real` para optar por fora."""
    if request.node.get_closest_marker("rede_real"):
        return

    async def _proibido(*args, **kwargs):
        raise AssertionError(
            "Teste tentou fazer uma chamada HTTP externa. Use um fake do provider "
            "ou marque o teste com @pytest.mark.rede_real se a chamada for intencional."
        )

    # Bloqueia o TRANSPORTE de rede, não o `AsyncClient`: o cliente de teste também
    # é um AsyncClient, só que sobre ASGITransport (em processo). Patchar a classe
    # inteira derrubaria os próprios testes de integração.
    monkeypatch.setattr(
        "httpx.AsyncHTTPTransport.handle_async_request", _proibido, raising=False
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "rede_real: permite que o teste faça chamadas HTTP externas de verdade"
    )
