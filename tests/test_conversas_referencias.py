"""
Referências sobrevivem ao reload da conversa.

Sintoma relatado: as fontes apareciam durante o streaming e sumiam ao reabrir a
conversa. Eram duas metades quebradas — o orquestrador nunca gravava as
citações, e o endpoint de detalhe não as devolvia mesmo quando existiam (caso
do agregador, que já gravava).

O teste central aqui é o de ida e volta: gravar, reler pelo endpoint, e
encontrar as referências. É ele que falhava antes.
"""

from datetime import UTC, datetime

import pytest

from app.models.models import Interaction, InteractionResponse

pytestmark = pytest.mark.asyncio


async def _interacao_com_resposta(db, conv, dono, *, extra_metadata=None, mode="PRODUCTIVITY"):
    """Uma pergunta e sua resposta, como o pipeline as grava."""
    interaction = Interaction(
        conversation_id=conv.id,
        user_id=dono.id,
        feature=conv.feature,
        mode=mode,
        prompt_text="monte uma anamnese",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(interaction)
    await db.flush()

    db.add(InteractionResponse(
        interaction_id=interaction.id,
        model_used="gpt-5.4-nano",
        response_text="Segue um modelo organizado de anamnese.",
        extra_metadata=extra_metadata,
    ))
    await db.flush()
    return interaction


async def test_citacoes_voltam_ao_reabrir_a_conversa(as_user, db, user, conversation_factory):
    """A regressão: antes, isto voltava sem `citations`."""
    conv = await conversation_factory(user)
    await _interacao_com_resposta(db, conv, user, extra_metadata={
        "citations": ["https://pubmed.gov/123", "https://diretrizes.org/x"],
    })

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    assert resp.status_code == 200

    assistente = [m for m in resp.json()["messages"] if m["role"] == "assistant"]
    assert assistente[0]["citations"] == [
        "https://pubmed.gov/123",
        "https://diretrizes.org/x",
    ]


async def test_pubmed_volta_com_as_duas_listas_separadas(as_user, db, user, conversation_factory):
    conv = await conversation_factory(user)
    await _interacao_com_resposta(db, conv, user, extra_metadata={
        "pubmed_validation": {
            "cited_verified": [
                {"title": "Confere", "pmid": "1", "verified": True},
                {"title": "Não confere", "pmid": "2", "verified": False},
            ],
            "newer_guidelines": [
                {"pmid": "9", "article_title": "Consenso 2026", "abstract_snippet": "trecho"},
            ],
        },
    })

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    validacao = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]["pubmed_validation"]

    # A distinção verificada/não-verificada é justamente o que a tabela
    # pubmed_validations não conseguia guardar.
    assert [c["verified"] for c in validacao["cited_verified"]] == [True, False]
    assert validacao["newer_guidelines"][0]["article_title"] == "Consenso 2026"


async def test_conversa_antiga_sem_metadata_nao_quebra(as_user, db, user, conversation_factory):
    """Não há backfill — respostas antigas têm a coluna nula e devem abrir."""
    conv = await conversation_factory(user)
    await _interacao_com_resposta(db, conv, user, extra_metadata=None)

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    assert resp.status_code == 200

    assistente = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    assert assistente["citations"] == []
    assert assistente["pubmed_validation"] is None


async def test_metadata_corrompido_nao_derruba_a_conversa(as_user, db, user, conversation_factory):
    """Um JSONB torto não deve custar a conversa inteira ao médico."""
    conv = await conversation_factory(user)
    await _interacao_com_resposta(db, conv, user, extra_metadata={"citations": "nao-e-lista"})

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    assert resp.status_code == 200
    assert [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]["citations"] == []


async def test_conversa_do_agregador_tambem_devolve_citacoes(as_user, db, user, conversation_factory):
    """O agregador já gravava em extra_metadata; faltava o endpoint devolver."""
    conv = await conversation_factory(user, feature="AGREGADOR")
    await _interacao_com_resposta(db, conv, user, extra_metadata={
        "citations": ["https://a.com"],
    })

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    assistente = [m for m in resp.json()["messages"] if m["role"] == "assistant"][0]
    assert assistente["citations"] == ["https://a.com"]


async def test_referencias_de_outro_usuario_seguem_inacessiveis(
    as_user, db, user_factory, conversation_factory
):
    """A mudança adiciona campos à resposta — não pode afrouxar a posse."""
    outro = await user_factory()
    conv = await conversation_factory(outro)
    await _interacao_com_resposta(db, conv, outro, extra_metadata={
        "citations": ["https://segredo.com"],
    })

    resp = await as_user.get(f"/api/v1/conversations/{conv.id}")
    assert resp.status_code == 404
    assert "segredo" not in resp.text
