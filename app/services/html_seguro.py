"""
HTML de post de notícia por LISTA DE PERMISSÃO.

O corpo do post é escrito por um modelo a partir de um abstract do PubMed — texto
de terceiro colado dentro de um prompt. Basta um abstract com instruções
embutidas para o redator devolver `<script>`, um `<img onerror=...>` ou um link
`javascript:`. Esse HTML era gravado como veio e a única barreira era o
sanitizador do navegador, na configuração padrão. Defesa em profundidade pede que
o servidor não ARMAZENE o que o cliente precisa torcer para filtrar.

Lista de permissão, não de bloqueio: o que o post precisa cabe em oito tags, e
toda tag fora delas some — inclusive as que ainda nem foram inventadas. Nenhum
atributo sobrevive (`style`, `on*`, `href`): o post não tem links no corpo, a
fonte é exibida à parte, e link dentro do iframe tiraria o médico da plataforma.

Sem dependência nova de propósito: o `HTMLParser` da biblioteca padrão dá conta
de um vocabulário deste tamanho.
"""

from html import escape
from html.parser import HTMLParser

TAGS_PERMITIDAS = frozenset({"p", "strong", "em", "ul", "ol", "li", "br", "h3"})
# O CONTEÚDO destas some junto com a tag — texto de script não é texto do post.
TAGS_DESCARTADAS_COM_CONTEUDO = frozenset({"script", "style", "iframe", "object", "embed", "noscript", "template"})
SEM_FECHAMENTO = frozenset({"br"})


class _Sanitizador(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.saida: list[str] = []
        self._ignorando = 0  # profundidade dentro de uma tag descartada com conteúdo

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in TAGS_DESCARTADAS_COM_CONTEUDO:
            self._ignorando += 1
        elif not self._ignorando and tag in TAGS_PERMITIDAS:
            self.saida.append(f"<{tag}>")  # atributos ficam de fora, todos

    def handle_startendtag(self, tag: str, attrs) -> None:
        if not self._ignorando and tag in TAGS_PERMITIDAS:
            self.saida.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in TAGS_DESCARTADAS_COM_CONTEUDO:
            self._ignorando = max(0, self._ignorando - 1)
        elif not self._ignorando and tag in TAGS_PERMITIDAS and tag not in SEM_FECHAMENTO:
            self.saida.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._ignorando:
            # As entidades já foram convertidas pelo parser; aqui voltam a ser
            # escapadas. `&lt;script&gt;` no texto continua sendo TEXTO.
            self.saida.append(escape(data, quote=False))


def sanitizar_html_de_post(html: str) -> str:
    """Devolve só as tags permitidas, sem atributos. Tag desconhecida perde a tag e mantém o texto."""
    parser = _Sanitizador()
    parser.feed(html or "")
    parser.close()
    return "".join(parser.saida)
