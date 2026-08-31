"""
Autorização de rotas (item 1.2 do plano de prontidão).

Duas garantias que antes existiam só por leitura de código:

1. Toda rota tem uma política de acesso DECLARADA. Uma rota nova sem entrada em
   `ROUTE_POLICY` faz o CI falhar — é a trava contra o esquecimento futuro, não
   só contra o erro de hoje.
2. Rota autenticada rejeita quem não deveria entrar: sem token, token inválido,
   token expirado, usuário inativo.

O isolamento entre contas (IDOR) fica em `test_idor.py`.
"""

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.main import app
from tests.conftest import auth_headers

PUBLICA = "publica"
AUTENTICADA = "autenticada"
ADMIN = "admin"

# Política de acesso de cada rota. Ao criar uma rota, declare-a aqui — o teste
# `test_toda_rota_tem_politica_declarada` falha enquanto isso não for feito.
ROUTE_POLICY: dict[tuple[str, str], str] = {
    # Público por natureza
    ("GET", "/api/v1/health"): PUBLICA,
    # Readiness é consultado pela plataforma, antes de existir usuário.
    ("GET", "/api/v1/health/ready"): PUBLICA,
    # Público porque são os fluxos de entrada — protegidos por rate limit,
    # OTP e validação server-to-server, não por token.
    ("POST", "/api/v1/auth/register"): PUBLICA,
    ("POST", "/api/v1/auth/otp/request"): PUBLICA,
    ("POST", "/api/v1/auth/otp/verify"): PUBLICA,
    ("POST", "/api/v1/auth/invite/accept"): PUBLICA,
    ("POST", "/api/v1/auth/embed/token"): PUBLICA,
    # Conta
    ("GET", "/api/v1/auth/me"): AUTENTICADA,
    ("PATCH", "/api/v1/auth/me"): AUTENTICADA,
    ("DELETE", "/api/v1/auth/me"): AUTENTICADA,
    # Portabilidade LGPD: cada titular exporta os PRÓPRIOS dados.
    ("GET", "/api/v1/auth/me/export"): AUTENTICADA,
    ("GET", "/api/v1/auth/me/consentimentos"): AUTENTICADA,
    ("POST", "/api/v1/auth/me/consentimentos/{tipo}/revogar"): AUTENTICADA,
    ("POST", "/api/v1/auth/onboarding"): AUTENTICADA,
    ("POST", "/api/v1/auth/invite/generate"): ADMIN,
    # Núcleo clínico
    ("POST", "/api/v1/orquestrador/query"): AUTENTICADA,
    ("POST", "/api/v1/orquestrador/stream"): AUTENTICADA,
    ("POST", "/api/v1/agregador/query"): AUTENTICADA,
    ("POST", "/api/v1/agregador/stream"): AUTENTICADA,
    ("GET", "/api/v1/agregador/models"): AUTENTICADA,
    ("GET", "/api/v1/agregador/history"): AUTENTICADA,
    # Conversas e pastas
    ("GET", "/api/v1/conversations"): AUTENTICADA,
    ("GET", "/api/v1/conversations/{conversation_id}"): AUTENTICADA,
    ("GET", "/api/v1/folders"): AUTENTICADA,
    ("POST", "/api/v1/folders"): AUTENTICADA,
    ("PUT", "/api/v1/folders/{folder_id}"): AUTENTICADA,
    ("DELETE", "/api/v1/folders/{folder_id}"): AUTENTICADA,
    ("PATCH", "/api/v1/folders/conversations/bulk"): AUTENTICADA,
    ("PATCH", "/api/v1/folders/conversations/{conversation_id}/folder"): AUTENTICADA,
    # Calculadoras
    ("GET", "/api/v1/calculators"): AUTENTICADA,
    ("GET", "/api/v1/calculators/{slug}"): AUTENTICADA,
    ("POST", "/api/v1/calculators/{slug}/execute"): AUTENTICADA,
    ("POST", "/api/v1/calculators/{slug}/extract"): AUTENTICADA,
    ("PUT", "/api/v1/calculators/{slug}/favorite"): AUTENTICADA,
    ("DELETE", "/api/v1/calculators/{slug}/favorite"): AUTENTICADA,
    ("GET", "/api/v1/calculators/{slug}/history"): AUTENTICADA,
    # PREVENT roda para um médico logado, como as demais calculadoras —
    # a rota declara Depends(get_current_user).
    ("POST", "/api/v1/prevent/calculate"): AUTENTICADA,
    # Landing pages: formulários de interesse abertos, preenchidos por quem
    # ainda NÃO tem conta — é esse o propósito da página. A proteção é rate
    # limit, como nos demais fluxos de entrada, não token.
    ("GET", "/api/v1/landing-pages/{slug}/check"): PUBLICA,
    ("POST", "/api/v1/landing-pages/finance/submit"): PUBLICA,
    ("POST", "/api/v1/landing-pages/accounting/submit"): PUBLICA,
    ("POST", "/api/v1/landing-pages/partners/submit"): PUBLICA,
    # Exceção entre as LPs: esta é o formulário exibido DENTRO do produto,
    # e declara Depends(get_current_user).
    ("POST", "/api/v1/landing-pages/calculators/submit"): AUTENTICADA,
    # Notícias. TUDO autenticado, sem exceção: o feed é personalizado, e a
    # versão anterior deste módulo identificava o leitor por `?email=` na query
    # string — forjável, e portanto suficiente para ler e alterar os temas de
    # outra pessoa. A leitura só parecia inofensiva enquanto o conteúdo era o
    # mesmo para todos.
    ("GET", "/api/v1/news/highlights"): AUTENTICADA,
    ("GET", "/api/v1/news/articles/{article_id}"): AUTENTICADA,
    ("GET", "/api/v1/news/me/topics"): AUTENTICADA,
    ("PUT", "/api/v1/news/me/topics"): AUTENTICADA,
    ("GET", "/api/v1/news/me/preferences"): AUTENTICADA,
    ("PUT", "/api/v1/news/me/preferences"): AUTENTICADA,
    ("GET", "/api/v1/news/favorites"): AUTENTICADA,
    ("POST", "/api/v1/news/favorites/toggle"): AUTENTICADA,
    ("POST", "/api/v1/news/feedback/nao-interessa"): AUTENTICADA,
    # Palavras-chave: são a lista de interesses da pessoa, tão pessoal quanto os
    # temas. O preview também exige token — sem isso, viraria um endpoint aberto
    # de busca sobre todo o acervo, chamável em rajada por qualquer um.
    ("GET", "/api/v1/news/me/keywords"): AUTENTICADA,
    ("POST", "/api/v1/news/me/keywords"): AUTENTICADA,
    ("DELETE", "/api/v1/news/me/keywords/{termo}"): AUTENTICADA,
    ("GET", "/api/v1/news/keywords/preview"): AUTENTICADA,
    # Dispara coleta, tagging e redação — ou seja, gasta Anthropic e OpenAI.
    ("POST", "/api/v1/news/admin/pipeline"): ADMIN,
    # Uploads e uso
    ("POST", "/api/v1/uploads/extract"): AUTENTICADA,
    ("GET", "/api/v1/users/usage"): AUTENTICADA,
}


def rotas_da_app() -> list[tuple[str, str]]:
    """
    Rotas expostas pela aplicação, lidas do schema OpenAPI.

    Usar o schema em vez de varrer `app.routes` é deliberado: a estrutura interna
    de rotas do FastAPI já mudou de forma (0.141 aninhou as rotas incluídas dentro
    de objetos de router, e uma varredura por `isinstance(..., APIRoute)` passou a
    devolver ZERO — silenciosamente transformando todo teste parametrizado por
    rota em no-op). O schema é contrato público e devolve o caminho completo.

    Limitação conhecida: rota declarada com `include_in_schema=False` não aparece
    aqui. Se algum dia for preciso uma, ela precisa de política declarada à mão.
    """
    schema = app.openapi()
    rotas = sorted(
        (metodo.upper(), caminho)
        for caminho, operacoes in schema["paths"].items()
        for metodo in operacoes
        if metodo.upper() not in {"HEAD", "OPTIONS"}
    )
    # Salvaguarda: varredura vazia faria os testes abaixo passarem vacuamente.
    assert rotas, "Nenhuma rota encontrada — a varredura quebrou, não a aplicação."
    return rotas


def rotas_com_politica(*politicas: str) -> list[tuple[str, str]]:
    return [r for r in rotas_da_app() if ROUTE_POLICY.get(r) in politicas]


# ── A trava anti-regressão ───────────────────────────────────────────────

def test_toda_rota_tem_politica_declarada():
    """
    Rota nova precisa de decisão explícita de acesso. Sem isso, uma rota criada
    sem `Depends(get_current_user)` entraria em produção aberta e silenciosa.
    """
    sem_politica = [r for r in rotas_da_app() if r not in ROUTE_POLICY]
    assert not sem_politica, (
        "Rota(s) sem política declarada em ROUTE_POLICY:\n  "
        + "\n  ".join(f"{m} {p}" for m, p in sem_politica)
        + "\n\nDeclare como PUBLICA, AUTENTICADA ou ADMIN em tests/test_authorization.py."
    )


def test_politica_nao_referencia_rota_inexistente():
    """Rota removida deve sair do mapa, senão ele vira ficção."""
    existentes = set(rotas_da_app())
    fantasmas = [r for r in ROUTE_POLICY if r not in existentes]
    assert not fantasmas, f"ROUTE_POLICY tem rotas que não existem mais: {fantasmas}"


# ── Rotas autenticadas rejeitam quem não deveria entrar ──────────────────

@pytest.mark.parametrize(("metodo", "caminho"), rotas_com_politica(AUTENTICADA, ADMIN))
async def test_sem_token_recebe_401(client, metodo, caminho):
    resp = await client.request(metodo, _preenche_params(caminho))
    assert resp.status_code == 401, (
        f"{metodo} {caminho} respondeu {resp.status_code} sem token — deveria ser 401."
    )


@pytest.mark.parametrize(("metodo", "caminho"), rotas_com_politica(AUTENTICADA, ADMIN))
async def test_token_com_assinatura_invalida_recebe_401(client, metodo, caminho):
    """Token assinado com outra chave não pode ser aceito."""
    token = pyjwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000001"}, "chave-errada-mas-longa-o-suficiente-para-hs256", algorithm="HS256"
    )
    resp = await client.request(
        metodo, _preenche_params(caminho), headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401


async def test_token_expirado_recebe_401(client, user):
    settings = get_settings()
    token = pyjwt.encode(
        {
            "sub": str(user.id),
            "role": user.role,
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_usuario_inativo_recebe_401(client, user_factory):
    """`status=False` derruba o acesso mesmo com token válido e não expirado."""
    inativo = await user_factory(status=False)
    resp = await client.get("/api/v1/auth/me", headers=auth_headers(inativo))
    assert resp.status_code == 401


async def test_usuario_inexistente_recebe_401(client):
    """Token bem assinado para um id que não existe mais no banco."""
    settings = get_settings()
    token = pyjwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111", "role": "beta_user"},
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── Rota restrita a admin ────────────────────────────────────────────────

async def test_usuario_comum_nao_gera_convite(client, user):
    resp = await client.post(
        "/api/v1/auth/invite/generate", json={"email": "novo@example.com"}, headers=auth_headers(user)
    )
    assert resp.status_code == 403


async def test_admin_gera_convite(client, admin):
    resp = await client.post(
        "/api/v1/auth/invite/generate", json={"email": "novo@example.com"}, headers=auth_headers(admin)
    )
    assert resp.status_code == 200
    assert "invite_url" in resp.json()


# ── Rotas públicas seguem públicas ───────────────────────────────────────

async def test_health_e_publica(client):
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_otp_request_nao_revela_se_email_existe(client):
    """Resposta idêntica para e-mail cadastrado e não cadastrado (anti-enumeração)."""
    r1 = await client.post("/api/v1/auth/otp/request", json={"email": "nao-existe@example.com"})
    r2 = await client.post("/api/v1/auth/otp/request", json={"email": "tambem-nao@example.com"})
    assert r1.status_code == r2.status_code == 204
    assert r1.content == r2.content


# ── Utilitário ───────────────────────────────────────────────────────────

_PARAMS_FICTICIOS = {
    "{conversation_id}": "00000000-0000-0000-0000-0000000000aa",
    "{folder_id}": "00000000-0000-0000-0000-0000000000bb",
    "{slug}": "calculadora-inexistente",
}


def _preenche_params(caminho: str) -> str:
    """
    Troca parâmetros de rota por valores fictícios.

    O recurso não precisa existir: a checagem de autenticação roda como dependency,
    antes do handler, então a resposta esperada é 401 independentemente do id.
    """
    for marcador, valor in _PARAMS_FICTICIOS.items():
        caminho = caminho.replace(marcador, valor)
    return caminho
