"""
Testes dos modelos de e-mail.

São funções puras — não tocam em rede nem em banco —, então dá para afirmar o
que interessa de verdade: que o código chega inteiro, que não há imagem (Gmail
e Outlook bloqueiam), que todo e-mail leva texto E html, e que um título de
artigo com `<` não escapa para dentro do HTML.
"""

import re
from types import SimpleNamespace

import pytest

from app.services import email_templates as t


def artigo(id=1, titulo="Um título", slug="lancet", original=None):
    return SimpleNamespace(
        id=id,
        rewritten_title=titulo,
        original_title=original or "Original",
        journal_slug=slug,
    )


TODOS_OS_HTML = "todos_os_html"


@pytest.fixture
def todos_os_html():
    """Os três e-mails, para as regras que valem para qualquer um deles."""
    _, otp_html = t.otp("418250", 10)
    _, convite_html = t.convite("https://exemplo.test/convite/abc")
    _, _, digest_html = t.digest("Ruben", [(artigo(), None)], "https://news.test")
    return {"otp": otp_html, "convite": convite_html, "digest": digest_html}


# ── regras que valem para os três ────────────────────────────────────────────

def test_nenhum_email_tem_imagem(todos_os_html):
    """Gmail e Outlook bloqueiam imagem embutida (data URI) e pedem autorização
    para as hospedadas. A primeira versão levava o "M" da marca como SVG em
    data URI e o que chegava era um quadradinho vazio ao lado do nome."""
    for nome, html in todos_os_html.items():
        assert "<img" not in html, f"{nome} tem <img>"
        assert "base64" not in html, f"{nome} tem data URI"


def test_nenhum_email_usa_style_no_head_nem_classe(todos_os_html):
    """O Gmail descarta boa parte do CSS do `<head>`; o que sobrevive é inline."""
    for nome, html in todos_os_html.items():
        assert "<style" not in html, f"{nome} tem <style>"
        assert "class=" not in html, f"{nome} usa classe CSS"


def test_todo_email_declara_light_only(todos_os_html):
    """Sem isso o modo escuro do Gmail/Outlook inverte as cores por conta
    própria e o Verde Menta vira um cinza sujo."""
    for nome, html in todos_os_html.items():
        assert 'content="light only"' in html, f"{nome} não declara color-scheme"


def test_todo_email_tem_a_assinatura_e_o_slogan(todos_os_html):
    for nome, html in todos_os_html.items():
        assert "Médico<span" in html, f"{nome} sem a assinatura Médico360"
        assert "com você em cada fase." in html, f"{nome} sem o slogan"


def test_tags_fecham_em_todos(todos_os_html):
    import html.parser

    class Checa(html.parser.HTMLParser):
        VAZIAS = {"img", "br", "meta", "hr", "input", "link"}

        def __init__(self):
            super().__init__()
            self.pilha, self.erros = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in self.VAZIAS:
                self.pilha.append(tag)

        def handle_endtag(self, tag):
            if tag in self.VAZIAS:
                return
            if not self.pilha or self.pilha[-1] != tag:
                self.erros.append(tag)
            else:
                self.pilha.pop()

    for nome, doc in todos_os_html.items():
        c = Checa()
        c.feed(doc)
        assert not c.erros and not c.pilha, f"{nome}: erros={c.erros} abertas={c.pilha}"


# ── código de acesso ─────────────────────────────────────────────────────────

def test_codigo_aparece_sem_espaco_no_meio():
    """Um "418 250" é copiado COM o espaço, e o backend valida `^\\d{6}$`. Os
    campos do frontend limpam não dígitos antes de enviar, mas construir a
    armadilha e confiar na rede de proteção seria pedir o incidente."""
    _, html = t.otp("418250", 10)
    # o código, exatamente como está, tem de existir no HTML
    assert "418250" in html
    # e não pode haver versão fatiada por espaço/tag no meio dos dígitos
    assert not re.search(r"418[^0-9]+250", html)


def test_codigo_vai_no_texto_e_no_html():
    texto, html = t.otp("418250", 10)
    assert "418250" in texto and "418250" in html


def test_minutos_vem_do_ajuste_nao_fixo():
    """Checa texto e HTML SEPARADAMENTE, e que o 10 antigo sumiu dos dois.

    A primeira versão deste teste só procurava "7 minutos" nas duas partes — e
    passava com o HTML fixo em "10 minutos", porque o texto puro (correto)
    também contém "7 minutos" e o `and` já estava satisfeito. Teste cego.
    """
    texto, html = t.otp("111111", 7)
    assert "7 minutos" in texto
    assert "7 minutos" in html
    assert "10 minutos" not in texto
    assert "10 minutos" not in html


# ── convite ──────────────────────────────────────────────────────────────────

def test_convite_leva_a_url_no_botao_e_no_texto():
    url = "https://exemplo.test/convite/abc123"
    texto, html = t.convite(url)
    assert url in texto
    assert f'href="{url}"' in html


# ── digest ───────────────────────────────────────────────────────────────────

def test_digest_mostra_o_nome_de_apresentacao_do_periodico():
    """O modelo guarda o slug ("lancet"); o leitor tem de ver "The Lancet"."""
    _, _, html = t.digest("Ruben", [(artigo(slug="lancet"), None)], "https://news.test")
    assert "The Lancet" in html
    assert ">lancet<" not in html


def test_digest_cai_para_o_slug_quando_o_periodico_e_desconhecido():
    _, _, html = t.digest("Ruben", [(artigo(slug="revista-nova"), None)], "https://news.test")
    assert "revista-nova" in html


def test_digest_diz_por_que_o_artigo_chegou():
    """É o que permite à pessoa saber exatamente o que desligar."""
    _, texto, html = t.digest(
        "Ruben", [(artigo(), "Estatinas")], "https://news.test"
    )
    assert "Estatinas" in html
    assert "Estatinas" in texto


def test_digest_sem_motivo_nao_mostra_selo_vazio():
    _, _, html = t.digest("Ruben", [(artigo(), None)], "https://news.test")
    assert "porque você acompanha" not in html


def test_digest_usa_o_primeiro_nome():
    _, texto, html = t.digest("Ruben Nogueira da Silva", [(artigo(), None)], "https://news.test")
    assert "Olá, Ruben!" in texto
    assert "Olá, Ruben!" in html
    assert "Nogueira" not in html


def test_digest_sem_nome_nao_quebra():
    _, texto, html = t.digest(None, [(artigo(), None)], "https://news.test")
    assert "Olá!" in texto and "Olá!" in html


def test_digest_singular_e_plural():
    assunto1, _, _ = t.digest("R", [(artigo(),  None)], "https://news.test")
    assunto2, _, _ = t.digest("R", [(artigo(1), None), (artigo(2), None)], "https://news.test")
    assert "1 destaque " in assunto1
    assert "2 destaques " in assunto2


def test_digest_cai_para_o_titulo_original_se_nao_houve_reescrita():
    """`rewritten_title` é anulável. Mandar a palavra "None" como manchete seria
    a falha silenciosa mais feia possível."""
    a = artigo(titulo=None, original="Título original do estudo")
    _, texto, html = t.digest("R", [(a, None)], "https://news.test")
    assert "Título original do estudo" in html
    assert "None" not in texto


def test_titulo_com_html_e_escapado():
    """Título vindo de fonte externa não pode injetar marcação no e-mail."""
    a = artigo(titulo='Estudo <script>alert(1)</script> sobre AVC')
    _, _, html = t.digest("R", [(a, None)], "https://news.test")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_motivo_com_html_e_escapado():
    _, _, html = t.digest("R", [(artigo(), '<b>x</b>')], "https://news.test")
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;" in html


def test_base_sem_barra_final_nao_duplica():
    _, texto, html = t.digest("R", [(artigo(id=9), None)], "https://news.test/")
    assert "https://news.test/artigo/9" in texto
    assert "//artigo" not in html
