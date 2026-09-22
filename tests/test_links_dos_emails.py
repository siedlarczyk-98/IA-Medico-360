"""
Os links que saem nos e-mails apontam para onde deveriam.

POR QUE ESTE ARQUIVO EXISTE
O digest chegou em produção com `localhost:5176` em todos os links. A causa
imediata era ambiente (`NOTICIAS_URL` não definida, caindo no default), mas o
que deixou passar foi não haver nada que olhasse o link pronto.

Um e-mail é a única parte do produto que o usuário recebe SEM estar na
plataforma: se o link estiver errado, não há como ele se corrigir navegando.

Dois riscos distintos, e os dois estão cobertos aqui:
  1. o link aponta para o app ERRADO (o convite usava `frontend_url`, o digest
     usa `noticias_url` — trocar os dois é fácil e silencioso);
  2. o link aponta para uma ROTA QUE NÃO EXISTE. Já aconteceu duas vezes neste
     repo: `/termos` no onboarding e `/artigo/:id` no digest, ambos caindo num
     catch-all que levava o usuário para outro lugar.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import email_templates as t

RAIZ = Path(__file__).resolve().parents[1]


def artigo(id=153):
    return SimpleNamespace(
        id=id,
        rewritten_title="Um destaque",
        original_title="Um destaque",
        journal_slug="lancet",
    )


def _links(html: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', html)


# ── o link sai com a base que recebeu ────────────────────────────────────────

def test_digest_usa_a_base_que_recebe_e_nao_uma_fixa():
    """O `localhost` que apareceu em produção veio de configuração, não de
    valor fixo no código — este teste é o que garante que continua assim."""
    _, texto, html = t.digest("R", [(artigo(), None)], "https://news.exemplo.app")

    assert "https://news.exemplo.app/artigo/153" in html
    assert "https://news.exemplo.app/artigo/153" in texto
    assert "localhost" not in html
    assert "localhost" not in texto


def test_convite_usa_a_url_que_recebe():
    _, html = t.convite("https://app.exemplo.com/invite?token=abc")
    assert "https://app.exemplo.com/invite?token=abc" in html
    assert "localhost" not in html


# ── as rotas existem de verdade ──────────────────────────────────────────────

def _rotas_do_noticias_app() -> set[str]:
    """As rotas declaradas em `noticias-app/src/App.tsx`.

    Lido do arquivo e não copiado para cá: uma cópia passaria a concordar
    consigo mesma e pararia de vigiar o frontend, que é o ponto.
    """
    texto = (RAIZ / "noticias-app" / "src" / "App.tsx").read_text(encoding="utf-8")
    return set(re.findall(r'<Route\s+path="([^"]+)"', texto))


def test_o_artigo_do_digest_tem_rota_no_app():
    """`/artigo/153` precisa abrir AQUELE destaque.

    Antes o app não tinha roteador nenhum: o link carregava o feed genérico e o
    médico tinha de procurar de novo o que acabara de escolher ler.
    """
    rotas = _rotas_do_noticias_app()
    assert "/artigo/:id" in rotas, f"rotas encontradas: {sorted(rotas)}"


def test_o_descadastro_do_digest_tem_rota_no_app():
    """`/preferencias` é o link de "parar de receber". É o que a lei espera que
    funcione, e o que mais custa caro se levar a lugar nenhum."""
    assert "/preferencias" in _rotas_do_noticias_app()


def test_o_destino_do_link_sobrevive_ao_login():
    """O link do digest abre FORA do iframe, então o médico costuma passar pelo
    login por código antes de chegar ao destaque.

    `temEntradaDireta()` é o que impede o destino de se perder nesse caminho:
    sem ele o app terminava o login e mandava para o feed genérico, e o médico
    tinha de procurar de novo o destaque que escolhera ler.

    O teste lê o código porque a regra é do frontend e este app não tem harness
    próprio (instalar jsdom exige gerar o lockfile em Linux). É verificação
    grosseira — não executa a função —, mas pega o caso que importa: alguém
    remover a checagem e o link voltar a cair no feed.
    """
    app = (RAIZ / "noticias-app" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "function temEntradaDireta" in app, (
        "sumiu a checagem que faz o link do e-mail sobreviver ao login"
    )
    # Os dois caminhos que o digest gera precisam estar reconhecidos nela.
    assert "'/artigo/'" in app and "'/preferencias'" in app

    # E ela precisa ser CHAMADA nos dois pontos que decidem o destino depois da
    # autenticação — o login por código e o reaproveitamento de sessão.
    #
    # Conta só as chamadas de verdade: a primeira versão deste teste usava
    # `app.count("temEntradaDireta()")`, e os comentários que citam a função
    # entravam na conta. Remover as duas chamadas continuava passando — o teste
    # media a documentação, não o código.
    codigo = "\n".join(
        linha for linha in app.splitlines()
        if not linha.lstrip().startswith(("//", "*", "/*"))
    )
    chamadas = len(re.findall(r"(?<!function )\btemEntradaDireta\(\)", codigo))
    assert chamadas >= 2, (
        f"a checagem existe mas é chamada {chamadas}x — precisa valer nos dois "
        "caminhos de entrada (login por código e sessão reaproveitada)"
    )


def test_todo_caminho_que_o_digest_gera_esta_coberto():
    """Varre os links REAIS do e-mail e confere cada caminho contra as rotas.

    Afirma sobre o que o template gera, não sobre uma lista escrita à mão: um
    link novo no e-mail entra nesta verificação sozinho.
    """
    base = "https://news.exemplo.app"
    _, _, html = t.digest("R", [(artigo(), None)], base)

    rotas = _rotas_do_noticias_app()
    assert "*" in rotas, (
        "o app perdeu o catch-all: caminho desconhecido passaria a dar tela "
        "branca em vez de cair no feed"
    )

    # O `*` atende qualquer caminho, inclusive a raiz — então ele sozinho faria
    # este teste passar sempre. Por isso a verificação é a INVERSA: todo link do
    # e-mail que NÃO é a raiz precisa de uma rota PRÓPRIA. Cair no catch-all é
    # exatamente o defeito que estamos caçando (o médico clica num destaque e
    # recebe o feed genérico).
    especificas = [
        re.compile("^" + re.sub(r":\w+", r"[^/]+", rota) + "$")
        for rota in rotas
        if rota != "*"
    ]

    for link in _links(html):
        if not link.startswith(base):
            continue  # link externo (documentos legais) — não é rota do app
        caminho = link[len(base) :] or "/"
        if caminho == "/":
            continue  # a home é o próprio feed, servida pelo catch-all
        assert any(p.match(caminho) for p in especificas), (
            f"o e-mail linka {caminho}, que cairia no catch-all do noticias-app "
            f"em vez de abrir o que promete (rotas: {sorted(rotas)})"
        )


# ── o app certo para cada e-mail ─────────────────────────────────────────────

@pytest.mark.parametrize(
    ("qual", "base"),
    [("digest", "https://news.exemplo.app"), ("convite", "https://app.exemplo.com")],
)
def test_cada_email_aponta_para_o_seu_proprio_app(qual, base):
    """Digest vai para o app de notícias; convite, para o app principal. São
    configurações diferentes (`NOTICIAS_URL` e `FRONTEND_URL`) e trocá-las é um
    erro que nenhum teste pegaria se este não existisse."""
    if qual == "digest":
        _, _, html = t.digest("R", [(artigo(), None)], base)
    else:
        _, html = t.convite(f"{base}/invite?token=abc")

    internos = [ln for ln in _links(html) if "paciente360.com.br" not in ln]
    assert internos, "nenhum link interno no e-mail"
    for link in internos:
        assert link.startswith(base), f"{qual} linkou {link}, fora de {base}"
