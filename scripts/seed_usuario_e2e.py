"""
Cria o usuario fixo que os testes E2E usam para assinar token.

O login real e por magic-link/OTP, que nao da para automatizar. Os testes E2E
assinam um token localmente para um usuario de UUID conhecido
(`calculadoras-app/e2e/helpers/auth.ts`) — mas ninguem criava esse usuario, entao
o token era valido e o `get_current_user` devolvia 401 mesmo assim.

Idempotente: rodar de novo nao duplica nem altera nada.

    python -m scripts.seed_usuario_e2e
"""

import asyncio
import os
import sys
import uuid

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.models import User

# Precisa bater com TEST_USER_ID de calculadoras-app/e2e/helpers/auth.ts
UUID_E2E = uuid.UUID(os.environ.get("E2E_TEST_USER_ID", "c7b85085-dcd7-437c-89ba-e419c16bcff8"))
EMAIL_E2E = "e2e@medico360.local"
ROLE_E2E = os.environ.get("E2E_TEST_USER_ROLE", "free_user")


async def main() -> int:
    async with async_session_factory() as db:
        existente = (await db.execute(select(User).where(User.id == UUID_E2E))).scalar_one_or_none()
        if existente:
            print(f"Usuario de E2E ja existe: {existente.email} ({existente.role})")
            return 0

        db.add(User(
            id=UUID_E2E,
            email=EMAIL_E2E,
            role=ROLE_E2E,
            status=True,
            onboarding_complete=True,
            name="Usuario E2E",
        ))
        await db.commit()

    print(f"Usuario de E2E criado: {EMAIL_E2E} ({ROLE_E2E}) id={UUID_E2E}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
