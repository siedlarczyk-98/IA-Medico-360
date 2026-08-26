"""
Metadados de referência da resposta: fontes citadas e validação PubMed.

Vive em `InteractionResponse.extra_metadata` (JSONB que já existe e já é usado
assim pelo agregador), e não em colunas novas — não precisa de migration.

Por que o PubMed também vem para cá, se existe a tabela `pubmed_validations`:
aquela tabela não distingue de forma confiável uma citação *verificada* de uma
*diretriz mais recente*. As duas são gravadas com `relevance_score=0.0` quando
a citação não foi verificada, e `abstract_snippet` pode ser nulo nos dois
casos. Ou seja, ela serve para análise, mas não permite reconstruir as duas
listas que a interface mostra separadamente. O JSONB guarda a forma exata que
a tela consome.

As funções ficam num módulo só porque `/query` e `/stream` precisam das duas —
e todo o resto que os dois compartilham já divergiu por ter sido copiado.
"""

from typing import Any


def build_response_metadata(
    *,
    pubmed: Any = None,
    citations: list[str] | None = None,
) -> dict | None:
    """
    Monta o `extra_metadata` de uma InteractionResponse.

    Devolve None quando não há nada a guardar, para não encher o banco de
    objetos vazios — a coluna é nullable e o leitor trata a ausência.

    `pubmed` é o resultado de `validate_with_pubmed` (duck-typed de propósito:
    o módulo não deve importar o serviço de PubMed só para uma anotação).
    """
    meta: dict = {}

    if citations:
        meta["citations"] = list(citations)

    if pubmed is not None:
        cited = [
            {"title": c.title, "pmid": c.pmid, "verified": c.verified}
            for c in getattr(pubmed, "cited_guidelines_verified", [])
        ]
        newer = [
            {
                "pmid": a.pmid,
                "article_title": a.article_title,
                "abstract_snippet": a.abstract_snippet or None,
            }
            for a in getattr(pubmed, "newer_guidelines_found", [])
        ]
        # Só grava se houver conteúdo: um bloco "Referências verificadas" vazio
        # na tela é pior que bloco nenhum.
        if cited or newer:
            meta["pubmed_validation"] = {
                "cited_verified": cited,
                "newer_guidelines": newer,
            }

    return meta or None


def read_response_metadata(extra_metadata: Any) -> tuple[list[str], dict | None]:
    """
    Lê `extra_metadata` de volta como (citations, pubmed_validation).

    Tolerante de propósito: conversas anteriores a esta mudança têm a coluna
    nula, e as do agregador têm só `citations`. Nenhum dos dois casos é erro —
    são respostas legítimas que simplesmente não têm referências guardadas.
    Não há backfill, então este caminho é permanente, não transitório.
    """
    if not isinstance(extra_metadata, dict):
        return [], None

    citations = extra_metadata.get("citations")
    if not isinstance(citations, list):
        citations = []

    pubmed = extra_metadata.get("pubmed_validation")
    if not isinstance(pubmed, dict):
        pubmed = None

    return citations, pubmed
