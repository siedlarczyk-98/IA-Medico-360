"""
Vocabulários que os frontends precisam conhecer.

Existe para que a lista de especialidades pare de viver hardcoded em
`frontend-app/src/pages/OnboardingPage.tsx`. Enquanto ela morava lá, o backend
não tinha vocabulário nenhum — aceitava qualquer string — e o teste da taxonomia
de notícias precisava LER O TSX COM REGEX para se validar.

Público de propósito: é a lista que a tela de cadastro precisa antes de existir
sessão, e não há nada sensível nela.
"""

from fastapi import APIRouter, Response

from app.medicina import especialidades

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/especialidades")
async def listar_especialidades(response: Response) -> list[dict[str, str]]:
    """Lista canônica `{slug, nome}`. Muda em escala de anos — cacheável à vontade."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return especialidades.para_api()
