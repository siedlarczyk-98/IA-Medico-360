"""
Todo app nosso consegue ESCREVER na API a partir do navegador.

O QUE ISTO VEIO CONSERTAR
A guarda anti-CSRF (`exigir_origem_confiavel`) cobre o router inteiro e recusa
qualquer `Origin` fora de `origens_confiaveis()`. O `dea_url` estava fora da
lista de propósito e o `noticias_url` nunca tinha entrado. Em produção, cadastrar
um DEA pelo navegador devolvia 403 (conferido em 2026-09-21), e notícias só
funcionava porque a URL tinha sido posta à mão numa variável de ambiente.

POR QUE NENHUM TESTE PEGOU
Todos os testes de escrita do DEA e de notícias chamavam a API SEM o header
`Origin` — que é exatamente o caminho que a guarda deixa passar. A produção
manda o header; o teste não mandava. `test_csrf_rotas_de_escrita.py` prova que
origem hostil é recusada; faltava o lado de cá: origem NOSSA é aceita.

As duas travas abaixo são estruturais. Rota nova ou app novo entram sozinhos.
"""

import pytest

from app.core.config import Settings, get_settings, origens_confiaveis
from app.main import app
from tests.test_csrf_rotas_de_escrita import _preenche_params, _rotas_de_escrita

# Toda configuração que termina em `_url` precisa estar em UM dos dois conjuntos.
# Campo novo sem classificação quebra `test_toda_url_das_configuracoes_esta_classificada`
# — que é o ponto: foi assim, por esquecimento, que `noticias_url` ficou de fora.
URLS_DE_FRONTEND = {"frontend_url", "calculadoras_url", "noticias_url", "dea_url"}
URLS_QUE_NAO_SAO_FRONTEND = {"database_url", "redis_url"}


def _origem_do_dono(caminho: str) -> str:
    """A origem do app que, em produção, é quem chama esta rota."""
    s = get_settings()
    if caminho.startswith("/api/v1/dea/"):
        return s.dea_url
    if caminho.startswith("/api/v1/news/"):
        return s.noticias_url
    if caminho.startswith("/api/v1/landing-pages/"):
        return s.landing_pages_origins[0]
    if caminho.startswith("/api/v1/calculators/"):
        return s.calculadoras_url
    return s.frontend_url


def test_toda_url_das_configuracoes_esta_classificada():
    urls = {nome for nome in Settings.model_fields if nome.endswith("_url")}
    sem_classe = urls - URLS_DE_FRONTEND - URLS_QUE_NAO_SAO_FRONTEND

    assert not sem_classe, (
        f"Configuração nova sem classificação: {sorted(sem_classe)}. Se é a URL de um "
        "app nosso, entra em URLS_DE_FRONTEND e em `origens_confiaveis()`; se não é, "
        "entra em URLS_QUE_NAO_SAO_FRONTEND."
    )


@pytest.mark.parametrize("campo", sorted(URLS_DE_FRONTEND))
def test_todo_frontend_e_origem_confiavel_e_esta_no_cors(campo):
    settings = get_settings()
    url = getattr(settings, campo)

    assert url in origens_confiaveis(settings), f"{campo} fora da guarda anti-CSRF"

    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert url in cors.kwargs["allow_origins"], f"{campo} fora do CORS"


def test_cors_e_guarda_usam_a_mesma_lista():
    """Eram duas listas montadas em lugares diferentes, e divergiram."""
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")

    assert list(cors.kwargs["allow_origins"]) == origens_confiaveis(get_settings())


@pytest.mark.parametrize(("metodo", "caminho"), _rotas_de_escrita())
async def test_toda_rota_de_escrita_aceita_a_origem_do_app_dono(client, metodo, caminho):
    """
    Sem autenticação e sem corpo, de propósito: a guarda de origem roda ANTES de
    autenticar e de validar. O que vier depois — 401, 422, 404 — prova que a
    origem passou, sem gravar nada. Só o 403 "Origem não autorizada" reprova.
    """
    resp = await client.request(
        metodo, _preenche_params(caminho), headers={"Origin": _origem_do_dono(caminho)}
    )

    recusada_pela_origem = resp.status_code == 403 and "origem" in resp.text.lower()
    assert not recusada_pela_origem, (
        f"{metodo} {caminho} recusou a origem do próprio app dono "
        f"({_origem_do_dono(caminho)}). No navegador isso é um 403 para todo usuário."
    )


# ── As duas provas executadas na varredura de 2026-09-18 ─────────────────────

async def test_cadastro_de_dea_pelo_navegador_nao_leva_403(client):
    resp = await client.post(
        "/api/v1/dea/locais", json={}, headers={"Origin": get_settings().dea_url}
    )

    assert resp.status_code == 422, "corpo vazio deve parar na validação, não na origem"


async def test_salvar_palavra_chave_de_noticia_nao_leva_403(client, user):
    from tests.conftest import auth_headers

    resp = await client.post(
        "/api/v1/news/me/keywords",
        json={},
        headers={**auth_headers(user), "Origin": get_settings().noticias_url},
    )

    assert resp.status_code == 422
