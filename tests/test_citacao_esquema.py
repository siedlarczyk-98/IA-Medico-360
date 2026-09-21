"""
Citação só com `http`/`https`.

A URL vem do provedor (busca na web) e vira `<a href>` no chat. Um `javascript:`
ali roda no navegador do médico com um clique (item 52 da varredura).
"""

import pytest

from app.core.citacoes_fonte import criar_citacao, normalizar, para_json


@pytest.mark.parametrize("url", [
    "javascript:alert(document.cookie)",
    "JaVaScRiPt:alert(1)",
    "  javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "//evil.com/sem-esquema",
    "pubmed.ncbi.nlm.nih.gov/123",
])
def test_esquema_perigoso_ou_ausente_e_descartado(url):
    assert criar_citacao(url, "Título") is None


@pytest.mark.parametrize("url", [
    "https://pubmed.ncbi.nlm.nih.gov/12345/",
    "http://www.scielo.br/artigo",
    "HTTPS://WWW.NEJM.ORG/doi/10.1056/x",
])
def test_http_e_https_passam(url):
    assert criar_citacao(url).url == url


def test_o_filtro_vale_na_releitura_do_historico():
    """Citação hostil que já esteja GRAVADA também não chega à tela."""
    gravadas = [
        {"url": "javascript:alert(1)", "title": "Clique aqui"},
        "data:text/html,x",
        {"url": "https://pubmed.ncbi.nlm.nih.gov/1/", "title": "Boa"},
    ]

    assert normalizar(gravadas) == [{"url": "https://pubmed.ncbi.nlm.nih.gov/1/", "title": "Boa"}]
    assert para_json(["javascript:alert(1)"]) is None
