"""
O 429 do rate limit fala português, na chave que os apps leem.

O handler padrão do slowapi responde `{"error": "Rate limit exceeded: ..."}`.
Nenhum app nosso lê `error` — todos mostram `detail` —, então bater num limite
aparecia para o médico como "Erro ao conectar com o servidor" (visto em produção
em 2026-09-21, durante a conferência da fase 0).
"""

from app.core.config import get_settings


async def test_429_traz_detail_em_portugues_e_preserva_os_cabecalhos(client):
    url = "/api/v1/landing-pages/finance/check?email=limite@example.com"

    respostas = [await client.get(url) for _ in range(61)]

    assert [r.status_code for r in respostas[:60]] == [200] * 60
    estourou = respostas[60]
    assert estourou.status_code == 429
    corpo = estourou.json()
    assert "Muitas requisições" in corpo["detail"]
    # A chave antiga continua, para quem já a lia.
    assert corpo["error"].startswith("Rate limit exceeded")
    assert int(estourou.headers["content-length"]) == len(estourou.content)


async def test_429_passa_pelo_cors_para_o_app_conseguir_ler(client):
    """Sem o header de CORS o browser esconde o corpo, e a frase não chega à tela."""
    url = "/api/v1/landing-pages/finance/check?email=cors@example.com"
    origem = {"Origin": get_settings().frontend_url}

    for _ in range(60):
        await client.get(url, headers=origem)
    estourou = await client.get(url, headers=origem)

    assert estourou.status_code == 429
    assert estourou.headers["access-control-allow-origin"] == get_settings().frontend_url
