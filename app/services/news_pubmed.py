"""
Médico 360 — Busca de artigos no PubMed para o módulo de Notícias.

Fonte ÚNICA de coleta. Não há fallback de scraping HTML: a versão anterior tinha
um, mas ele produzia "artigos" sem abstract a partir de qualquer link da página
do journal, e o redator então escrevia um post inteiro em cima de um título
solto. Ver `app/news/journals.py` para o histórico completo.

Fluxo: ESearch (PMIDs recentes daquele ISSN) -> EFetch (detalhes em XML).

Os parâmetros comuns (chave, identificação) vêm de `pubmed_eutils`, que é
compartilhado com o validador de citações do orquestrador — os dois consomem o
mesmo rate limit da NCBI.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree

from app.core.http_client import get_client
from app.services.pubmed_eutils import EUTILS_BASE, eutils_params

logger = logging.getLogger(__name__)

_MESES = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


@dataclass
class ArtigoPubMed:
    """Artigo vindo do PubMed, antes de virar linha no banco."""

    pmid: str
    title: str
    abstract: str | None
    authors: list[str]
    doi: str | None
    published_date: datetime | None
    # [{"descriptor": "Obesity", "major": True}, ...] — vazio é o caso COMUM em
    # item recém-publicado: a indexação MEDLINE atrasa semanas.
    mesh_terms: list[dict] = field(default_factory=list)

    @property
    def source_url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


async def buscar_artigos_por_issn(
    issn: str,
    dias_atras: int = 10,
    max_resultados: int = 40,
    timeout: int = 20,
) -> list[ArtigoPubMed]:
    """
    Busca os artigos mais recentes publicados sob o ISSN dado.

    `dias_atras=10` é intencionalmente maior que 7: journals atrasam indexação, e
    uma janela mais larga com deduplicação por (source, external_id) no banco é
    mais segura que perder uma semana inteira.

    `max_resultados=40` e não 15: a NEJM intercala muito conteúdo sem abstract
    nas posições mais recentes (cartas, réplicas, perspectivas), o que empurra os
    artigos de pesquisa para fora de um teto baixo antes mesmo do filtro.

    Levanta `httpx.HTTPError` se a NCBI falhar — quem chama decide o que fazer.
    Ver `news_collector_service.coletar_para_journal`, que trata como coleta zero.
    """
    client = get_client()

    desde = (datetime.now(UTC) - timedelta(days=dias_atras)).strftime("%Y/%m/%d")
    ate = datetime.now(UTC).strftime("%Y/%m/%d")

    search_params = eutils_params(
        db="pubmed",
        term=f'"{issn}"[ISSN] AND ("{desde}"[PDAT] : "{ate}"[PDAT])',
        retmode="json",
        retmax=str(max_resultados),
        sort="pub+date",
    )

    resp = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=search_params, timeout=timeout)
    resp.raise_for_status()
    pmids = resp.json().get("esearchresult", {}).get("idlist", [])

    if not pmids:
        logger.info("PubMed: nenhum PMID para ISSN %s nos últimos %d dias", issn, dias_atras)
        return []

    fetch_params = eutils_params(
        db="pubmed",
        id=",".join(pmids),
        retmode="xml",
        rettype="abstract",
    )
    fetch_resp = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=fetch_params, timeout=timeout)
    fetch_resp.raise_for_status()

    return _parse_efetch(fetch_resp.text)


def _parse_efetch(xml_text: str) -> list[ArtigoPubMed]:
    root = ElementTree.fromstring(xml_text)
    artigos: list[ArtigoPubMed] = []

    for node in root.findall(".//PubmedArticle"):
        try:
            artigo = _parse_artigo(node)
            if artigo:
                artigos.append(artigo)
        except Exception:
            # Um item malformado não pode derrubar a coleta dos outros 39.
            logger.exception("Falha ao parsear um artigo do PubMed; pulando este item")
            continue

    return artigos


def _parse_artigo(node: ElementTree.Element) -> ArtigoPubMed | None:
    medline = node.find(".//MedlineCitation")
    if medline is None:
        return None

    pmid_el = medline.find("PMID")
    if pmid_el is None or not pmid_el.text:
        return None

    article_el = medline.find("Article")
    if article_el is None:
        return None

    title_el = article_el.find("ArticleTitle")
    title = "".join(title_el.itertext()).strip() if title_el is not None else "(sem título)"

    # O abstract vem em partes rotuladas (BACKGROUND, METHODS, ...). Preservar os
    # rótulos importa: é por eles que `is_editorial_or_secondary_piece` distingue
    # artigo de pesquisa de peça editorial.
    partes = []
    for parte in article_el.findall(".//Abstract/AbstractText"):
        label = parte.get("Label")
        texto = "".join(parte.itertext()).strip()
        partes.append(f"{label}: {texto}" if label else texto)
    abstract = "\n\n".join(partes) if partes else None

    authors: list[str] = []
    for autor in article_el.findall(".//AuthorList/Author"):
        sobrenome = autor.findtext("LastName")
        nome = autor.findtext("ForeName")
        if sobrenome:
            authors.append(f"{nome} {sobrenome}".strip() if nome else sobrenome)

    doi = None
    for id_el in node.findall(".//ArticleIdList/ArticleId"):
        if id_el.get("IdType") == "doi":
            doi = id_el.text
            break

    return ArtigoPubMed(
        pmid=pmid_el.text,
        title=title,
        abstract=abstract,
        authors=authors,
        doi=doi,
        published_date=_parse_data(article_el),
        mesh_terms=_parse_mesh(medline),
    )


def _parse_mesh(medline: ElementTree.Element) -> list[dict]:
    """
    Extrai os descritores MeSH, marcando quais são tópico principal do artigo.

    `MajorTopicYN="Y"` é o que o indexador da NLM considerou o assunto central —
    distinção que o tagger usa para não tratar um descritor periférico com o
    mesmo peso do tema principal.

    Lista vazia é normal e esperado: artigo ahead-of-print ainda não foi indexado.
    """
    termos: list[dict] = []
    for heading in medline.findall(".//MeshHeadingList/MeshHeading"):
        descritor = heading.find("DescriptorName")
        if descritor is None or not descritor.text:
            continue
        termos.append({
            "descriptor": descritor.text.strip(),
            "major": descritor.get("MajorTopicYN") == "Y",
        })
    return termos


def _parse_data(article_el: ElementTree.Element) -> datetime | None:
    date_el = article_el.find(".//Journal/JournalIssue/PubDate")
    if date_el is None:
        return None

    ano = date_el.findtext("Year")
    if not ano:
        return None

    mes = date_el.findtext("Month") or "01"
    dia = date_el.findtext("Day") or "01"

    mes_num = _MESES.get(mes, mes if mes.isdigit() else "01")
    dia_num = dia if dia.isdigit() else "01"

    try:
        return datetime(int(ano), int(mes_num), int(dia_num), tzinfo=UTC)
    except ValueError:
        return datetime(int(ano), 1, 1, tzinfo=UTC)
