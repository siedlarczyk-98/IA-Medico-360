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
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    # Necessário em SQLAlchemy async: com expire_on_commit=True, acessar um atributo
    # após o commit dispara lazy-load implícito, que é proibido em contexto async
    # (MissingGreenlet). Efeito colateral: objetos podem ficar com dados stale após
    # commit se o mesmo objeto for reutilizado sem `db.refresh()` — mitigar chamando
    # `await db.refresh(obj)` explicitamente quando o valor pós-commit importar.
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
