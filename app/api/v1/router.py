from fastapi import APIRouter, Depends

from app.api.deps import exigir_origem_confiavel
from app.api.v1.endpoints.agregador import router as agregador_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.conversations import router as conversations_router
from app.api.v1.endpoints.folders import router as folders_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.landing_pages import router as landing_pages_router
from app.api.v1.endpoints.meta import router as meta_router
from app.api.v1.endpoints.news import router as news_router
from app.api.v1.endpoints.orquestrador import router as orquestrador_router
from app.api.v1.endpoints.uploads import router as uploads_router
from app.api.v1.endpoints.usage import router as usage_router
from app.calculators.routers.calculators_router import router as calculators_router
from app.calculators.routers.prevent_router import router as prevent_router
from app.dea.routers.dea_router import router as dea_router

# Anti-CSRF por CLASSE, não rota a rota.
#
# O cookie de sessão é `SameSite=None` (iframe da Waid), então viaja cross-site.
# A defesa que existia dependia de o handler declarar parâmetro de corpo — o que
# força `application/json` e, por tabela, preflight. Handler SEM body param não
# impõe content-type nenhum e era alcançável por `<form>` cross-site: eram seis
# rotas assim, entre elas a revogação de consentimento, que grava recusa
# permanente no registro que serve de prova (LGPD Art. 8º §5º).
#
# Declarada aqui, no router que agrega TODOS os endpoints, porque o furo não era
# uma rota esquecida e sim a ausência de regra: rota de escrita nova precisa
# nascer protegida sem ninguém lembrar de nada. `exigir_origem_confiavel` ignora
# métodos idempotentes, então GET/HEAD cross-origin seguem funcionando.
api_v1_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(exigir_origem_confiavel)],
)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(conversations_router)
api_v1_router.include_router(folders_router)
api_v1_router.include_router(agregador_router)
api_v1_router.include_router(calculators_router)
api_v1_router.include_router(prevent_router)
api_v1_router.include_router(dea_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(landing_pages_router)
api_v1_router.include_router(meta_router)
api_v1_router.include_router(news_router)
api_v1_router.include_router(orquestrador_router)
api_v1_router.include_router(uploads_router)
api_v1_router.include_router(usage_router, prefix="/users", tags=["usage"])
