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

# Métodos que não mudam estado. `Origin` hostil neles não é CSRF: o atacante
# dispara a leitura mas não lê a resposta (o CORS bloqueia), e nada é gravado.
METODOS_IDEMPOTENTES = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


async def exigir_origem_confiavel(request: Request) -> None:
    """Barra requisição de ESCRITA vinda de origem que não é nossa.

    POR QUE ISTO EXISTE
    `get_current_user` aceita o JWT no cookie `medico360_session`, emitido com
    `SameSite=None` (obrigatório para os apps rodarem dentro do iframe da
    Waid). Um cookie assim viaja em requisição cross-site — é a definição de
    CSRF.

    POR QUE ELA VALE PARA TODAS AS ROTAS, E NÃO SÓ PARA O UPLOAD
    A premissa antiga era: "a maioria dos endpoints está acidentalmente
    protegida, porque exige `Content-Type: application/json`, que não é um
    content-type simples de CORS, logo o browser dispara preflight". Isso É
    verdade para handler que declara parâmetro de corpo — e SÓ para ele.

    Um handler SEM body param não impõe content-type nenhum: o FastAPI não tem
    o que validar, o browser não faz preflight, e um `<form>` cross-site chega
    com o cookie anexado. Havia seis rotas nessa situação (as duas emissíveis
    por `<form>` — que só sabe GET e POST — sendo
    `POST /auth/me/consentimentos/{tipo}/revogar` e
    `POST /news/admin/pipeline`; as outras quatro são PUT/DELETE, alcançáveis
    apenas por `fetch`, que preflighta).

    A da revogação de consentimento é a grave: grava manifestação de vontade
    NEGATIVA, permanente e falsamente atribuída, no registro que o próprio
    docstring da rota chama de prova (LGPD Art. 8º §5º).

    Por isso a guarda é aplicada como dependency do router inteiro
    (`app/api/v1/router.py`) e filtra por método aqui dentro — em vez de ser
    declarada rota a rota. Rota de escrita nova nasce protegida; a alternativa
    depende de alguém lembrar, e foi exatamente o que falhou antes.

    O caso original (`/uploads/extract`, `multipart/form-data`) continua
    coberto: um médico logado que abrisse página hostil teria quota consumida,
    custo de API cobrado da conta dele e `FileExtraction` de conteúdo alheio
    gravado sob o `user_id` dele — material que depois aparece no export LGPD
    como se fosse dado do titular.

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
    if request.method.upper() in METODOS_IDEMPOTENTES:
        return

    origem = request.headers.get("origin")
    if origem is None:
        return
    if origem not in origens_confiaveis(settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origem não autorizada.",
        )
