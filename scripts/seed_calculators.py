"""Seed inicial do módulo de calculadoras: especialidade Cardiologia."""

import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.calculators import Specialty


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(Specialty).where(Specialty.slug == "cardiologia"))
        specialty = result.scalar_one_or_none()
        if specialty is None:
            specialty = Specialty(name="Cardiologia", slug="cardiologia")
            db.add(specialty)
            await db.flush()

        await db.commit()
        print("Seed concluído.")


if __name__ == "__main__":
    asyncio.run(main())
