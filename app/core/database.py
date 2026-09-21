"""
Médico 360 — Conexão async com PostgreSQL via SQLAlchemy 2.0.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug and not settings.is_production,
    pool_size=30,
    max_overflow=10,
    pool_pre_ping=True,
    # Pool esgotado tem de falhar RÁPIDO. O padrão é esperar 30 s por uma conexão:
    # com o banco saturado, toda requisição autenticada ficava meio minuto
    # pendurada antes de devolver 500, e a fila de espera mantinha o pool
    # saturado mesmo depois de a causa passar. 5 s devolve o erro enquanto o
    # usuário ainda está olhando, e deixa o pool se recuperar.
    pool_timeout=5,
    connect_args={
        "server_settings": {
            # Rede de segurança, não ajuste fino: nenhuma transação deveria ficar
            # parada — o stream solta a conexão antes de chamar o modelo (ver
            # `orquestrador_stream_service`). Se um caminho novo voltar a prender
            # conexão ociosa, o Postgres a derruba em 3 min em vez de deixá-la
            # segurando bloqueio indefinidamente. Folgado de propósito: o `/query`
            # ainda espera o modelo dentro da transação.
            "idle_in_transaction_session_timeout": "180000",
        },
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    # Evita o lazy-load pós-commit (MissingGreenlet em async). Em troca, use
    # `await db.refresh(obj)` quando o valor pós-commit importar.
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency injection para rotas FastAPI."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
