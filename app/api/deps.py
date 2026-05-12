"""
Médico 360 — Dependencies de autenticação.
Extrai usuário autenticado do token JWT.
"""

from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import User

settings = get_settings()
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extrai e valida o usuário a partir do token JWT."""
    
    # Debug para ver no painel do Railway o que está chegando
    if credentials:
        print(f"--- DEBUG RAILWAY ---")
        print(f"Token recebido (10 chars): {credentials.credentials[:10]}...")

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não fornecido",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: campo 'sub' ausente",
            )
    except JWTError as e:
        print(f"Erro JWT: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
        )

    # Busca no banco de dados
    try:
        result = await db.execute(
            select(User).where(User.id == UUID(user_id), User.status == True)
        )
        user = result.scalar_one_or_none()
    except Exception as e:
        print(f"Erro ao buscar no banco: {str(e)}")
        raise HTTPException(status_code=500, detail="Erro interno ao acessar banco")

    if not user:
        print(f"Usuário {user_id} não encontrado no banco do Railway!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )
        
    return user