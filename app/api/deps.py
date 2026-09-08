"""
Médico 360 — Dependencies de autenticação.
Extrai usuário autenticado do token JWT.
"""

from uuid import UUID

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, origens_confiaveis
from app.core.database import get_db
from app.models.models import User

settings = get_settings()
COOKIE_NAME = "medico360_session"
security = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extrai e valida o usuário a partir do token JWT (header Authorization ou cookie SSO)."""

    raw_token = credentials.credentials if credentials else request.cookies.get(COOKIE_NAME)

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não fornecido",
        )

    token = raw_token.strip().replace("\n", "").replace("\r", "")

    try:
        payload = pyjwt.decode(
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
        try:
            user_uuid = UUID(user_id)
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
            )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

    result = await db.execute(
        select(User).where(User.id == user_uuid, User.status.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou inativo",
        )
        
    return user

async def exigir_origem_confiavel(request: Request) -> None:
    """Barra requisição de escrita vinda de origem que não é nossa.

    POR QUE ISTO EXISTE
    `get_current_user` aceita o JWT no cookie `medico360_session`, emitido com
    `SameSite=None` (obrigatório para os apps rodarem dentro do iframe da
    Waid). Um cookie assim viaja em requisição cross-site — é a definição de
    CSRF.

    A maioria dos endpoints está ACIDENTALMENTE protegida: eles exigem
    `Content-Type: application/json`, que não é um content-type "simples" de
    CORS, então o browser dispara um preflight `OPTIONS` que a allowlist do
    `CORSMiddleware` rejeita para origens estranhas.

    `/uploads/extract` era a exceção: ele recebe `multipart/form-data`, um dos
    três content-types simples. Um `<form>` cross-site não gera preflight, e o
    browser mandava o cookie junto. Um médico logado que abrisse uma página
    hostil teria a quota consumida, custo de API cobrado da conta dele (o
    caminho de imagem chama o Haiku e faz `record_cost`) e `FileExtraction` de
    conteúdo alheio gravado sob o `user_id` dele — material que depois aparece
    no export LGPD como se fosse dado do titular.

    O atacante não conseguia LER a resposta (o CORS bloqueia), então não era
    vazamento; era escrita e custo dirigidos por terceiro.

    POR QUE ORIGIN, E NÃO UM HEADER CUSTOMIZADO
    Exigir `X-Requested-With` também forçaria preflight, mas depende de todo
    cliente lembrar de enviá-lo — e um cliente que esquece falha ABERTO num
    caso e fechado no outro, dependendo do browser. `Origin` é preenchido pelo
    próprio navegador em toda requisição cross-site e não é falsificável por
    script.

    Ausência de `Origin` é permitida de propósito: requisição same-origin em
    alguns browsers, e chamadas server-to-server (scripts, testes, integrações)
    não têm origem — e também não carregam cookie de sessão de ninguém.
    """
    origem = request.headers.get("origin")
    if origem is None:
        return
    if origem not in origens_confiaveis(settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origem não autorizada.",
        )
