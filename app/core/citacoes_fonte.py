"""
Fontes citadas pelos provedores de busca.

POR QUE ESTE MÓDULO EXISTE
--------------------------
O campo `citations` nasceu como `list[str]` — só a URL. Os quatro provedores
(Anthropic, OpenAI, Google, Perplexity) sempre enviaram também o TÍTULO do
resultado, e a extração descartava: a tela mostrava
`https://pubmed.ncbi.nlm.nih.gov/42661420/` onde cabia o nome do artigo.

Passar a carregar o título mexe em oito pontos de extração, na persistência, no
schema e no front. Concentrar a forma do dado aqui evita que cada provider
invente o seu dicionário e que o formato divirja sem ninguém perceber.

A COMPATIBILIDADE É PERMANENTE, NÃO TRANSITÓRIA
-----------------------------------------------
As conversas gravadas antes desta mudança estão no JSONB de
`InteractionResponse.extra_metadata` como lista de strings. **Não há backfill**:
descobrir o título de uma URL antiga exigiria uma requisição por fonte contra
sites que podem ter saído do ar, mudado de layout ou entrado em paywall — e o
ganho seria estético, numa conversa que já foi lida.

Então `normalizar()` aceita os dois formatos para sempre. O front faz o mesmo
(`frontend-app/src/lib/citacoes.ts`) e mostra o domínio quando não há título.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

ESQUEMAS_PERMITIDOS = frozenset({"http", "https"})


@dataclass(frozen=True, slots=True)
class Citacao:
    """Uma fonte citada. `titulo` é `None` quando o provedor não mandou."""

    url: str
    titulo: str | None = None

    def para_dict(self) -> dict[str, str | None]:
        return {"url": self.url, "title": self.titulo}


def criar_citacao(url: str | None, titulo: str | None = None) -> Citacao | None:
    """
    Constrói uma citação, descartando o que não serve.

    URL vazia devolve `None` — sem endereço não há fonte, e um item sem link na
    lista é ruído. Título vazio ou só espaço vira `None` em vez de `""`: os
    provedores às vezes mandam string vazia, e o front trata ausência, não
    vazio.
    """
    if not url or not url.strip():
        return None
    url = url.strip()
    # Só `http` e `https`. A URL vem do provedor (Perplexity, busca na web) e vira
    # `<a href>` no chat: um `javascript:` ou `data:` ali roda no navegador do
    # médico com um clique. Esta função é o ponto único por onde toda citação
    # passa — na extração, na gravação e na releitura do histórico.
    if urlsplit(url).scheme.lower() not in ESQUEMAS_PERMITIDOS:
        return None
    limpo = titulo.strip() if titulo else None
    return Citacao(url=url, titulo=limpo or None)


def para_json(
    citacoes: list[Citacao] | list[str] | list[dict] | None,
) -> list[dict[str, str | None]] | None:
    """
    Forma serializável, para gravar no JSONB e mandar no SSE.

    Aceita `Citacao`, a URL crua e o dicionário já pronto. A tolerância não é
    preguiça: esta função fica nas BORDAS (persistência e SSE), onde chegam
    tanto objetos recém-extraídos de um provider quanto valores relidos de um
    cache ou de um payload antigo. Fazer cada chamador adivinhar o que tem em
    mãos é o que produz o `AttributeError` em produção, num caminho que o teste
    não cobria.
    """
    if not citacoes:
        return None
    return normalizar(citacoes) or None


def normalizar(brutas: object) -> list[dict[str, str | None]]:
    """
    Aceita qualquer um dos dois formatos gravados e devolve o novo.

    Tolera o legado (`["https://..."]`), o atual (`[{"url": ..., "title": ...}]`)
    e a mistura dos dois na mesma lista — que acontece de verdade quando uma
    conversa antiga recebe mensagem nova. Entrada inesperada é ignorada em vez
    de estourar: perder uma fonte é ruim, derrubar a leitura de uma conversa
    inteira é pior.
    """
    if not isinstance(brutas, list):
        return []

    saida: list[dict[str, str | None]] = []
    for item in brutas:
        if isinstance(item, Citacao):
            citacao = criar_citacao(item.url, item.titulo)
        elif isinstance(item, str):
            citacao = criar_citacao(item)
        elif isinstance(item, dict):
            citacao = criar_citacao(item.get("url"), item.get("title"))
        else:
            continue
        if citacao is not None:
            saida.append(citacao.para_dict())
    return saida
