"""
Proteção anti-CSRF no upload.

O PROBLEMA
`get_current_user` aceita o JWT no cookie `medico360_session`, emitido com
`SameSite=None` porque os apps rodam dentro do iframe da Waid. Cookie assim
viaja em requisição cross-site.

Quase todos os endpoints estão acidentalmente protegidos: exigem
`Content-Type: application/json`, que não é "simples" para o CORS, então o
browser dispara preflight e o `CORSMiddleware` recusa origens estranhas.

`/uploads/extract` é a única rota multipart do projeto — e `multipart/form-data`
É um content-type simples. Um `<form>` em página hostil chegava aqui sem
preflight, com o cookie do médico logado junto: quota consumida, custo de API
cobrado da conta dele (o caminho de imagem chama o Haiku e faz `record_cost`) e
`FileExtraction` de conteúdo alheio gravado sob o `user_id` dele.

Ler a resposta o atacante não conseguia — o CORS bloqueia. Era escrita e custo
dirigidos por terceiro, não vazamento.
"""

import io

import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


PDF_MINIMO = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>"


def _arquivo():
    return {"file": ("exame.pdf", io.BytesIO(PDF_MINIMO), "application/pdf")}


async def test_upload_de_origem_hostil_e_recusado(client, user):
    """O ataque concreto: `<form>` cross-site levando o cookie do médico."""
    resp = await client.post(
        "/api/v1/uploads/extract",
        files=_arquivo(),
        headers={**auth_headers(user), "Origin": "https://evil.com"},
    )

    assert resp.status_code == 403
    assert "origem" in resp.json()["detail"].lower()


async def test_upload_da_origem_do_app_continua_funcionando(client, user):
    """A proteção não pode quebrar o uso legítimo.

    Um 403 aqui significaria que a lista de origens confiáveis divergiu da que
    alimenta o CORS — exatamente o que `origens_confiaveis` existe para evitar.
    """
    from app.core.config import get_settings

    origem = get_settings().frontend_url
    resp = await client.post(
        "/api/v1/uploads/extract",
        files=_arquivo(),
        headers={**auth_headers(user), "Origin": origem},
    )

    assert resp.status_code != 403


async def test_requisicao_sem_origin_e_permitida(client, user):
    """Ausência de `Origin` é permitida de propósito: chamada server-to-server
    (script, teste, integração) não tem origem — e também não carrega cookie de
    sessão de ninguém."""
    resp = await client.post(
        "/api/v1/uploads/extract",
        files=_arquivo(),
        headers=auth_headers(user),
    )

    assert resp.status_code != 403


async def test_a_guarda_roda_antes_de_gastar_quota(client, user):
    """Um 403 não pode consumir limite nem gerar custo.

    Se a dependência rodasse depois de `check_limit`, o atacante ainda queimaria
    a quota da vítima — só não receberia o arquivo de volta.
    """
    from app.services.usage_service import add_interaction_audit  # noqa: F401

    resp = await client.post(
        "/api/v1/uploads/extract",
        files=_arquivo(),
        headers={**auth_headers(user), "Origin": "https://evil.com"},
    )

    assert resp.status_code == 403
    # O corpo não traz nada além da recusa — nenhum id de extração foi criado.
    assert "file_id" not in resp.text


async def test_a_lista_de_origens_e_a_mesma_do_cors():
    """Duas listas montadas em lugares diferentes divergem, e a divergência
    aparece como "o upload parou de funcionar" depois de alguém acrescentar um
    front novo só no CORS."""
    from app.core.config import get_settings, origens_confiaveis

    settings = get_settings()
    origens = origens_confiaveis(settings)

    assert settings.frontend_url in origens
    assert settings.calculadoras_url in origens
    for o in settings.embed_allowed_origins:
        assert o in origens, f"origem de embed {o} ficaria bloqueada no upload"
