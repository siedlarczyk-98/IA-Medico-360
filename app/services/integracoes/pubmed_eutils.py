"""
Médico 360 — Base compartilhada do PubMed E-utilities (NCBI).

POR QUE ESTE MÓDULO EXISTE
Dois consumidores batem no mesmo E-utilities com a MESMA chave da NCBI:

  - `app/services/pubmed_service.py` — valida citações do orquestrador.
  - `app/services/news_collector_service.py` — coleta os destaques dos journals.

O rate limit da NCBI é por chave (3 req/s sem chave, 10 req/s com). Com dois
clientes montando os próprios parâmetros, ninguém tem visão do orçamento comum e
o segundo a chegar leva 429 sem entender por quê. Aqui mora a única definição de
como se fala com a NCBI: base URL, credencial e identificação.

O QUE ESTE MÓDULO NÃO FAZ
Não define o formato dos artigos. Os dois consumidores têm necessidades
diferentes de parse (um quer título+snippet para conferir citação, o outro quer
abstract+autores+MeSH para redigir), e forçá-los num tipo comum só criaria um
objeto que não serve bem a nenhum dos dois.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# A NCBI pede que ferramentas automatizadas se identifiquem. Não é opcional nas
# boas práticas deles: sem isso, um pico de tráfego nosso vira bloqueio por IP
# sem que ninguém consiga nos avisar antes.
TOOL_NAME = "medico360"


def eutils_params(**extra: str) -> dict:
    """
    Monta os parâmetros comuns a toda chamada E-utilities, somando os específicos.

    A chave vem de `settings.pubmed_api_key` — a mesma que o validador de
    citações já usava. Uma chave só, um rate limit só, um lugar só para trocar.
    """
    settings = get_settings()

    params: dict = {"tool": TOOL_NAME}

    if settings.pubmed_api_key:
        params["api_key"] = settings.pubmed_api_key
    if settings.ncbi_contact_email:
        params["email"] = settings.ncbi_contact_email

    params.update(extra)
    return params
