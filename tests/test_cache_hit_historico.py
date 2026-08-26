"""
Resposta vinda do cache semântico também entra no histórico.

Antes, o caminho de cache hit retornava antes de criar conversa e interação: a
mensagem inteira sumia do histórico, não só as referências. E o payload
devolvido carregava `conversation_id`/`interaction_id` da interação que POPULOU
o cache — de outro usuário, já que o cache é global por modo.

Cobre também `build_metadata_from_cached`, que preserva as referências da
resposta original ao servi-la do cache.
"""

import pytest

from app.services.response_metadata import build_metadata_from_cached, read_response_metadata

pytestmark = pytest.mark.asyncio


PAYLOAD_CACHEADO = {
    "response_text": "Resposta previamente calculada.",
    "model_used": "sonar-pro",
    "conversation_id": "11111111-1111-1111-1111-111111111111",
    "interaction_id": "22222222-2222-2222-2222-222222222222",
    "citations": ["https://pubmed.gov/777"],
    "cited_guidelines_verified": [{"title": "Diretriz X", "pmid": "5", "verified": True}],
    "newer_guidelines_found": [{"pmid": "6", "title": "Consenso novo", "abstract_snippet": "trecho"}],
    "confidence_score": 0.9,
    "specialty_detected": "neurologia",
    "topic_detected": "cefaleia",
}


async def test_metadata_do_cache_preserva_citacoes():
    meta = build_metadata_from_cached(PAYLOAD_CACHEADO)
    citations, pubmed = read_response_metadata(meta)

    assert citations == ["https://pubmed.gov/777"]
    assert pubmed["cited_verified"][0]["pmid"] == "5"


async def test_metadata_do_cache_aceita_title_no_lugar_de_article_title():
    # O done_payload grava a chave como `title`; a UI espera `article_title`.
    meta = build_metadata_from_cached(PAYLOAD_CACHEADO)
    assert meta["pubmed_validation"]["newer_guidelines"][0]["article_title"] == "Consenso novo"


async def test_metadata_do_cache_sem_referencias_devolve_none():
    assert build_metadata_from_cached({"response_text": "oi"}) is None
    assert build_metadata_from_cached(None) is None


async def test_payload_cacheado_torto_nao_quebra():
    # response_json vem do banco; um registro antigo pode ter forma diferente.
    meta = build_metadata_from_cached({
        "citations": "nao-e-lista",
        "cited_guidelines_verified": ["nao-e-dict"],
        "newer_guidelines_found": None,
    })
    assert meta is None
