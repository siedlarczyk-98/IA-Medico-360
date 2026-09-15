"""
Anti-CSRF em TODA rota de escrita — a trava por classe.

O QUE ISTO VEIO CONSERTAR
A defesa anterior valia por acidente: handler que declara parâmetro de corpo
exige `Content-Type: application/json`, que não é um content-type "simples" de
CORS, então o browser dispara preflight e o `CORSMiddleware` recusa origem
estranha. `tests/test_csrf_upload.py` cobria a única exceção conhecida — a rota
multipart.

Só que a premissa não vale para handler SEM body param: não há o que o FastAPI
valide, não há content-type exigido, não há preflight, e um `<form>` cross-site
chega com o cookie `medico360_session` anexado. Havia SEIS rotas nessa situação,
em quatro arquivos — duas delas emissíveis por `<form>` (que só sabe GET e POST):

    POST   /auth/me/consentimentos/{tipo}/revogar   <-- a grave
    POST   /news/admin/pipeline
    DELETE /folders/{folder_id}
    DELETE /news/me/keywords/{termo}
    PUT    /calculators/{slug}/favorite
    DELETE /calculators/{slug}/favorite

A da revogação é a que dói: grava manifestação de vontade NEGATIVA, permanente e
falsamente atribuída, no registro que o próprio docstring da rota chama de prova
(LGPD Art. 8º §5º).

POR QUE O TESTE É ASSIM
`test_toda_rota_de_escrita_recusa_origem_hostil` não lista rotas: ele ENUMERA o
OpenAPI e exercita todas. Listar rotas à mão reproduziria o defeito original —
alguém acrescenta a sétima e ninguém lembra. É o mesmo mecanismo de
`tests/test_authorization.py`.
"""

import pytest

from app.api.deps import METODOS_IDEMPOTENTES
from app.main import app
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio

ORIGEM_HOSTIL = "https://evil.com"

# As seis que existiam quando a guarda foi escrita. Não é a fonte de verdade do
# teste abaixo (que enumera o OpenAPI) — é documentação do que motivou a
# correção, e detecta se alguma delas sumir sem querer.
ROTAS_SEM_BODY_PARAM = [
    ("POST", "/api/v1/auth/me/consentimentos/{tipo}/revogar"),
    ("POST", "/api/v1/news/admin/pipeline"),
    ("DELETE", "/api/v1/folders/{folder_id}"),
    ("DELETE", "/api/v1/news/me/keywords/{termo}"),
    ("PUT", "/api/v1/calculators/{slug}/favorite"),
    ("DELETE", "/api/v1/calculators/{slug}/favorite"),
]


def _rotas_de_escrita() -> list[tuple[str, str]]:
    """Toda rota não-idempotente do app, lida do schema OpenAPI."""
    schema = app.openapi()
    rotas = sorted(
        (metodo.upper(), caminho)
        for caminho, operacoes in schema["paths"].items()
        for metodo in operacoes
        if metodo.upper() not in METODOS_IDEMPOTENTES
    )
    assert rotas, "Nenhuma rota de escrita encontrada — a varredura quebrou."
    return rotas


def _preenche_params(caminho: str) -> str:
    """Troca `{param}` por um valor plausível. O 403 tem de vir ANTES do 404."""
    return (
        caminho.replace("{folder_id}", "00000000-0000-0000-0000-000000000001")
        .replace("{conversation_id}", "00000000-0000-0000-0000-000000000001")
        .replace("{interaction_id}", "00000000-0000-0000-0000-000000000001")
        .replace("{file_id}", "00000000-0000-0000-0000-000000000001")
        .replace("{article_id}", "1")
        .replace("{tipo}", "uso_clinico")
        .replace("{termo}", "cardiologia")
        .replace("{slug}", "chadsvasc")
        .replace("{alert_id}", "00000000-0000-0000-0000-000000000001")
    )


@pytest.mark.parametrize(("metodo", "caminho"), _rotas_de_escrita())
async def test_toda_rota_de_escrita_recusa_origem_hostil(client, user, metodo, caminho):
    """
    A trava da classe inteira: nenhuma rota de escrita pode aceitar `Origin`
    hostil, independentemente de declarar corpo ou não.

    Uma rota nova que escape disso faz este teste falhar — que é o ponto.
    """
    resp = await client.request(
        metodo,
        _preenche_params(caminho),
        headers={**auth_headers(user), "Origin": ORIGEM_HOSTIL},
    )

    assert resp.status_code == 403, (
        f"{metodo} {caminho} respondeu {resp.status_code} com Origin hostil — "
        "deveria ser 403. A guarda é dependency do `api_v1_router`."
    )
    assert "origem" in resp.json()["detail"].lower()


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_SEM_BODY_PARAM)
async def test_rotas_sem_body_param_estao_protegidas(client, user, metodo, caminho):
    """
    As seis nominalmente. Redundante com o teste acima por construção, e é essa
    a intenção: se a enumeração do OpenAPI quebrar (já aconteceu com `app.routes`
    no upgrade do FastAPI 0.141 — ver `test_authorization.rotas_da_app`), este
    aqui continua cobrindo os casos que motivaram a correção.
    """
    resp = await client.request(
        metodo,
        _preenche_params(caminho),
        headers={**auth_headers(user), "Origin": ORIGEM_HOSTIL},
    )

    assert resp.status_code == 403


async def test_revogacao_de_consentimento_nao_grava_de_origem_hostil(client, user, db):
    """
    O caso concreto, verificado pelo EFEITO e não pelo status: o registro de
    consentimento não pode ganhar uma recusa vinda de página hostil.

    É o pior dos seis porque o dado gravado é manifestação de vontade — e o
    docstring da rota chama esse registro de prova.
    """
    from sqlalchemy import func, select

    from app.models.models import ConsentLog
    from app.services import consent_service

    antes = await db.scalar(
        select(func.count()).select_from(ConsentLog).where(ConsentLog.user_id == user.id)
    )

    resp = await client.post(
        f"/api/v1/auth/me/consentimentos/{consent_service.USO_DADOS_ANONIMIZADOS}/revogar",
        headers={**auth_headers(user), "Origin": ORIGEM_HOSTIL},
    )

    assert resp.status_code == 403

    depois = await db.scalar(
        select(func.count()).select_from(ConsentLog).where(ConsentLog.user_id == user.id)
    )
    assert depois == antes, "A revogação foi gravada apesar da origem hostil"


# ── O que a guarda NÃO pode quebrar ──────────────────────────────────────


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_SEM_BODY_PARAM)
async def test_origem_do_app_continua_funcionando(client, user, admin, metodo, caminho):
    """
    Um 403 aqui significaria que a lista de origens confiáveis divergiu da que
    alimenta o CORS — exatamente o que `origens_confiaveis` existe para evitar.

    `/news/admin/pipeline` exige `role == "admin"` e responde 403 para quem não
    é — mesmo status da recusa por origem. Usar o usuário comum ali tornaria o
    teste ambíguo: ele passaria a "detectar" um 403 que nada tem a ver com CSRF.
    """
    from app.core.config import get_settings

    quem = admin if caminho.endswith("/admin/pipeline") else user

    resp = await client.request(
        metodo,
        _preenche_params(caminho),
        headers={**auth_headers(quem), "Origin": get_settings().frontend_url},
    )

    assert resp.status_code != 403


async def test_leitura_cross_origin_nao_e_barrada(client, user):
    """
    `GET` com origem estranha não é CSRF: nada é gravado, e o atacante não lê a
    resposta (o CORS bloqueia). Barrar aqui quebraria integração legítima sem
    ganho de segurança — por isso `exigir_origem_confiavel` ignora idempotentes.
    """
    resp = await client.get(
        "/api/v1/conversations",
        headers={**auth_headers(user), "Origin": ORIGEM_HOSTIL},
    )

    assert resp.status_code != 403


async def test_escrita_sem_origin_continua_permitida(client, user):
    """
    Ausência de `Origin` é permitida de propósito: chamada server-to-server
    (script, teste, integração) não tem origem — e também não carrega cookie de
    sessão de ninguém. Vale para as rotas sem body param como para as demais.
    """
    resp = await client.put(
        "/api/v1/calculators/chadsvasc/favorite",
        headers=auth_headers(user),
    )

    assert resp.status_code != 403
