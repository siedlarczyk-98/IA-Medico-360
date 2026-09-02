"""
Médico 360 — Agente Coletor de notícias.

Responsabilidade única: para o journal do dia, buscar itens novos no PubMed e
persistir como Article(status=collected). Não decide o que fazer com o conteúdo
depois — isso é do Tagger e do Redator.
"""

import logging
from datetime import UTC, datetime
from xml.etree.ElementTree import ParseError

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import Article, ArticleStatus
from app.news.journals import JournalConfig, journal_for_today
from app.services.integracoes.news_pubmed import ArtigoPubMed, buscar_artigos_por_issn

logger = logging.getLogger(__name__)

# Marcadores de estrutura de abstract científico. Genérico e portável entre
# journals: um artigo de pesquisa quase sempre tem ao menos uma dessas seções.
# Peças editoriais (réplicas, resumos, humanidades) tipicamente não têm abstract,
# ou têm texto livre sem nenhuma dessas seções.
MARCADORES_ESTRUTURA = (
    "IMPORTANCE",
    "OBJECTIVE",
    "BACKGROUND",
    "METHODS",
    "DESIGN",
    "RESULTS",
    "CONCLUSION",
)


def eh_peca_editorial(item: ArtigoPubMed, journal_slug: str) -> tuple[bool, str]:
    """
    Decide se um item é peça editorial/secundária (descartar) ou artigo de
    pesquisa (manter).

    Regra conservadora e igual para todos os journals: mantém se houver abstract
    com ao menos um marcador estrutural. Ponto de extensão: quando houver dados
    reais por journal, acrescentar exceções por `journal_slug` aqui, sem
    reescrever a lógica genérica.

    Retorna (é_secundária, motivo) — o motivo só serve para log.
    """
    if not item.abstract or not item.abstract.strip():
        return True, "abstract vazio ou ausente"

    if not any(marcador in item.abstract.upper() for marcador in MARCADORES_ESTRUTURA):
        return True, "abstract presente mas sem marcador de estrutura científica"

    return False, ""


async def coletar_do_dia(db: AsyncSession) -> dict:
    """Ponto de entrada do job diário. Retorna resumo do que foi coletado."""
    weekday = datetime.now(UTC).weekday()
    journal = journal_for_today(weekday)

    if journal is None:
        logger.info("Nenhum journal configurado para o dia %d (fim de semana)", weekday)
        return {"journal": None, "coletados": 0, "falhou": False}

    return await coletar_para_journal(db, journal)


async def coletar_para_journal(db: AsyncSession, journal: JournalConfig) -> dict:
    """
    Coleta um journal específico.

    SOBRE A FALHA DA NCBI SER TRATADA AQUI
    A versão anterior deixava a exceção subir: NCBI fora do ar ou 429 derrubava o
    job inteiro, e o "fallback" que parecia cobrir isso só cobria o caso raro de
    resposta 200 com lista vazia. O cenário provável não tinha cobertura nenhuma.

    Agora a falha vira coleta zero, registrada. Quem percebe que isso virou
    rotina é `vigilancia_service`, não um stacktrace que ninguém lê.
    """
    logger.info("Coletando %s (ISSN %s)", journal.display_name, journal.issn)

    try:
        artigos = await buscar_artigos_por_issn(journal.issn)
    except (httpx.HTTPError, ParseError) as exc:
        logger.warning(
            "Coleta de %s falhou ao consultar o PubMed: %s", journal.slug, exc
        )
        return {"journal": journal.slug, "coletados": 0, "falhou": True, "erro": str(exc)[:500]}

    salvos = await _persistir(db, journal, artigos)

    if artigos and salvos == 0:
        logger.warning(
            "Coleta de %s: PubMed devolveu %d item(ns), 0 salvo(s) "
            "(todos descartados como editorial ou já existentes)",
            journal.slug, len(artigos),
        )

    logger.info("Coleta de %s concluída: %d novo(s)", journal.slug, salvos)
    return {"journal": journal.slug, "coletados": salvos, "falhou": False}


async def _persistir(db: AsyncSession, journal: JournalConfig, artigos: list[ArtigoPubMed]) -> int:
    candidatos = []
    for item in artigos:
        secundaria, motivo = eh_peca_editorial(item, journal.slug)
        if secundaria:
            logger.info(
                "Descartando item não-científico: pmid=%s journal=%s motivo=%s titulo=%r",
                item.pmid, journal.slug, motivo, item.title,
            )
            continue
        candidatos.append(item)

    if not candidatos:
        return 0

    # Um único SELECT para todos os PMIDs. O banco é remoto: uma query por artigo
    # custava dezenas de round-trips por coleta.
    existentes = set(
        await db.scalars(
            select(Article.external_id).where(
                Article.source == "pubmed",
                Article.external_id.in_([item.pmid for item in candidatos]),
            )
        )
    )

    salvos = 0
    for item in candidatos:
        if item.pmid in existentes:
            continue  # idempotência

        db.add(
            Article(
                journal_slug=journal.slug,
                source="pubmed",
                external_id=item.pmid,
                doi=item.doi,
                source_url=item.source_url,
                original_title=item.title,
                original_abstract=item.abstract,
                authors="; ".join(item.authors) if item.authors else None,
                published_date=item.published_date,
                mesh_terms=item.mesh_terms or None,
                status=ArticleStatus.COLLECTED.value,
            )
        )
        salvos += 1

    if salvos:
        await db.flush()
    return salvos
