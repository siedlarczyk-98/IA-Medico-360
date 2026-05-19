"""
Médico 360 — Validação Científica via PubMed (Etapa 4 do Orquestrador).

Pipeline (duas trilhas paralelas):
  Trilha A: extrai citações da resposta do Claude → verifica cada uma no PubMed
  Trilha B: busca guidelines publicadas nos últimos 24 meses sobre o mesmo tópico
             → detecta diretrizes pós-cutoff do modelo (outdated_alert)

Confidence score baseado em fatos verificáveis, não em cosine similarity.

Regras atendidas:
  RN-ORC-003: busca PMIDs reais, sinaliza não verificado
  Seção 7: timeout 15s com fallback "sem validação + alerta"
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_API_KEY = getattr(settings, "pubmed_api_key", "")

CLINICAL_MODES = {"QUICK_SEARCH", "CLINICAL_REASONING"}


# ── Tipos ─────────────────────────────────────────────────────────────────────

@dataclass
class PubMedArticle:
    pmid: str
    article_title: str
    abstract_snippet: str
    relevance_score: float = 0.0


@dataclass
class VerifiedCitation:
    title: str        # como aparece na resposta do Claude
    pmid: str | None  # None se não encontrada no PubMed
    verified: bool


@dataclass
class ValidationResult:
    confidence_score: float
    cited_guidelines_verified: list[VerifiedCitation] = field(default_factory=list)
    newer_guidelines_found: list[PubMedArticle] = field(default_factory=list)
    outdated_alert: bool = False      # True se há guidelines mais novas que o Claude não citou
    low_evidence_alert: bool = False  # True se score < 0.5
    fallback: bool = False
    strict_filter_used: bool = True   # sempre True nesse pipeline


# ── Passo 1: Extrair citações da resposta ────────────────────────────────────

async def _extract_citations(client: httpx.AsyncClient, agent_response: str) -> list[str]:
    """
    Pede ao GPT-4o-mini para extrair as referências de guidelines/diretrizes
    mencionadas na resposta clínica. Retorna lista de strings brutas.
    """
    resp = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 300,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract all references cited in the medical text below. Include: "
                        "(1) clinical guidelines and official recommendations, "
                        "(2) landmark/seminal scientific papers cited with author names. "
                        "Return a JSON array of strings. For guidelines use the title as cited. "
                        "For papers with authors use format 'Author et al. Journal Year' "
                        "(e.g. 'Graus et al. Lancet Neurol 2016'). "
                        "Ignore vague mentions without a specific reference. "
                        'Example: ["2022 AHA/ACC/HFSA Heart Failure Guideline", '
                        '"Graus et al. Lancet Neurol 2016", '
                        '"Diretriz Brasileira de IC 2018"]. '
                        "Return an empty array [] if none are found."
                    ),
                },
                {"role": "user", "content": agent_response[:3000]},
            ],
        },
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"] or "[]"

    # extrai o array JSON mesmo que venha com texto extra
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return []


# ── Trilha A: Verificar citações no PubMed ───────────────────────────────────

_STOP_WORDS = {
    "the", "for", "of", "and", "in", "on", "with", "a", "an", "to", "from",
    "at", "by", "or", "is", "are", "was", "were", "its", "their", "this",
    "guidelines", "guideline", "practice", "clinical", "management",
    "treatment", "diagnosis", "international", "national", "consensus",
    "recommendations", "statement", "care", "update", "society", "american",
    "european", "brazilian", "heart", "failure",  # muito genérico isolado
}


def _build_keyword_query(citation: str) -> str:
    """Extrai 3-4 termos clínicos significativos da citação para busca fallback."""
    # remove abreviações entre parênteses: "(Sepsis-3)" → ""
    text = re.sub(r"\([^)]+\)", "", citation)
    # remove pontuação e anos
    text = re.sub(r"[\"\',\.\-/]|\b\d{4}\b", " ", text)
    words = [w for w in text.split() if w.lower() not in _STOP_WORDS and len(w) > 3]
    key_terms = words[:4]
    return " AND ".join(key_terms) if key_terms else citation[:80]


async def _verify_citation(
    client: httpx.AsyncClient, citation: str
) -> VerifiedCitation:
    """
    Busca uma citação no PubMed em duas tentativas:
    1. Título exato via [tiab]
    2. Fallback com 3-4 termos-chave + filtro de guideline/consensus
    """
    clean = re.sub(r"[\"']", "", citation)[:200]
    base_params = {"db": "pubmed", "retmax": "1", "retmode": "json", "sort": "relevance"}
    if PUBMED_API_KEY:
        base_params["api_key"] = PUBMED_API_KEY

    author_match = re.match(r"^([A-Za-z]+)", clean)
    year_match = re.search(r"\b(19|20)\d{2}\b", clean)

    if author_match and year_match and "et al" in clean.lower():
        # formato "Autor et al. Journal Ano" → autor + ano é suficientemente preciso
        author = author_match.group(1)
        year = year_match.group(0)
        searches = [f"{author}[author] AND {year}[pdat]"]
    else:
        searches = [
            f"{clean}[tiab]",
            f"{_build_keyword_query(citation)} AND "
            f'("guideline"[pt] OR "practice guideline"[pt] OR "consensus"[tiab])',
        ]

    try:
        for term in searches:
            res = await client.get(
                f"{PUBMED_BASE}/esearch.fcgi",
                params={**base_params, "term": term},
            )
            res.raise_for_status()
            pmids = res.json().get("esearchresult", {}).get("idlist", [])
            if pmids:
                return VerifiedCitation(title=citation, pmid=pmids[0], verified=True)
    except Exception as exc:
        logger.debug("[PubMed] Erro verificando citação '%s': %s", citation[:60], exc)

    return VerifiedCitation(title=citation, pmid=None, verified=False)


async def _verify_all_citations(
    client: httpx.AsyncClient, citations: list[str]
) -> list[VerifiedCitation]:
    """Verifica todas as citações em paralelo."""
    if not citations:
        return []
    results = await asyncio.gather(
        *[_verify_citation(client, c) for c in citations],
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, VerifiedCitation)]


# ── Trilha B: Buscar guidelines recentes no PubMed ───────────────────────────

async def _fetch_recent_guidelines(
    client: httpx.AsyncClient,
    topic: str,
    verified_pmids: set[str],
) -> list[PubMedArticle]:
    """
    Busca guidelines publicadas nos últimos 24 meses sobre o tópico.
    Filtra as que já foram citadas e verificadas (são novidades reais).
    """
    # traduz tópico PT→EN de forma simples substituindo termos comuns
    # (evita uma chamada LLM extra — o tópico já vem do specialty_detector)
    params = {
        "db": "pubmed",
        "term": (
            f'{topic} AND ("guideline"[pt] OR "practice guideline"[pt]) '
            f'AND "last 2 years"[dp] AND hasabstract[text]'
        ),
        "retmax": "3",
        "retmode": "json",
        "sort": "relevance",
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY

    try:
        res = await client.get(f"{PUBMED_BASE}/esearch.fcgi", params=params)
        res.raise_for_status()
        pmids = res.json().get("esearchresult", {}).get("idlist", [])

        # remove PMIDs já verificados nas citações do Claude
        new_pmids = [p for p in pmids if p not in verified_pmids]
        if not new_pmids:
            return []

        return await _fetch_article_titles(client, new_pmids)
    except Exception as exc:
        logger.debug("[PubMed] Erro buscando guidelines recentes: %s", exc)
        return []


async def _fetch_article_titles(
    client: httpx.AsyncClient, pmids: list[str]
) -> list[PubMedArticle]:
    """Busca títulos e snippets dos PMIDs via efetch XML."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY

    res = await client.get(f"{PUBMED_BASE}/efetch.fcgi", params=params)
    res.raise_for_status()

    articles = []
    for block in res.text.split("<PubmedArticle>")[1:]:
        pmid_m = re.search(r"<PMID[^>]*>(\d+)</PMID>", block)
        title_m = re.search(r"<ArticleTitle>([^<]+)</ArticleTitle>", block)
        abstract_m = re.search(r"<AbstractText[^>]*>([\s\S]*?)</AbstractText>", block)
        if pmid_m:
            abstract = ""
            if abstract_m:
                abstract = re.sub(r"<[^>]+>", "", abstract_m.group(1))[:400]
            articles.append(PubMedArticle(
                pmid=pmid_m.group(1),
                article_title=title_m.group(1) if title_m else "Título não disponível",
                abstract_snippet=abstract,
            ))
    return articles


# ── Passo 3: Calcular confidence_score ───────────────────────────────────────

def _calculate_score(
    verified: list[VerifiedCitation],
    newer: list[PubMedArticle],
) -> float:
    """
    Score baseado em fatos verificáveis. Recompensa verificações, não pune ausências
    (diretrizes brasileiras/regionais são válidas mas não estão no PubMed).

      Sem citações na resposta        → 0.10
      Citações presentes (base)       → 0.60
      +0.10 por citação verificada    → max +0.30
      +0.10 se sem guidelines novas   → resposta atualizada
      -0.15 por guideline mais nova   → modelo desatualizado
    """
    if not verified:
        return 0.10

    n_verified = sum(1 for c in verified if c.verified)
    up_to_date_bonus = 0.10 if not newer else 0.0
    penalty = 0.15 * len(newer)

    score = 0.60 + min(n_verified * 0.10, 0.30) + up_to_date_bonus - penalty
    return round(max(score, 0.10), 2)


# ── Pipeline interno ──────────────────────────────────────────────────────────

async def _run_validation(agent_response: str, topic: str) -> ValidationResult:
    async with httpx.AsyncClient(timeout=12.0) as client:

        # Passo 1: extrai citações da resposta
        citations = await _extract_citations(client, agent_response)
        logger.debug("[PubMed] Citações extraídas: %s", citations)

        if not citations:
            return ValidationResult(
                confidence_score=0.10,
                low_evidence_alert=True,
            )

        # Trilha A + Trilha B em paralelo
        verified, newer = await asyncio.gather(
            _verify_all_citations(client, citations),
            _fetch_recent_guidelines(
                client,
                topic or agent_response[:100],
                verified_pmids=set(),  # placeholder — preenchido abaixo
            ),
        )

        # remove das novidades os PMIDs que já foram verificados
        verified_pmids = {c.pmid for c in verified if c.pmid}
        newer = [a for a in newer if a.pmid not in verified_pmids]

    confidence = _calculate_score(verified, newer)

    return ValidationResult(
        confidence_score=confidence,
        cited_guidelines_verified=verified,
        newer_guidelines_found=newer,
        outdated_alert=len(newer) > 0,
        low_evidence_alert=confidence < 0.5,
        fallback=False,
        strict_filter_used=True,
    )


# ── Entrada pública ───────────────────────────────────────────────────────────

async def validate_with_pubmed(
    agent_response: str,
    mode: str = "",
    topic: str = "",
    timeout_s: float = 15.0,
) -> ValidationResult:
    """
    Valida a resposta clínica via duas trilhas paralelas no PubMed.
    Modos não clínicos (PHARMA_CHECK, PRODUCTIVITY) retornam fallback imediato.
    """
    if mode and mode not in CLINICAL_MODES:
        return ValidationResult(confidence_score=0.0, fallback=True)

    try:
        return await asyncio.wait_for(
            _run_validation(agent_response, topic),
            timeout=timeout_s,
        )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.warning("[PubMed] Fallback ativado: %s", exc)
        return ValidationResult(confidence_score=0.0, low_evidence_alert=True, fallback=True)
