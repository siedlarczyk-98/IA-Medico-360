"""
O contexto não pode contaminar a chave do cache semântico.

A separação entre "prompt que vai para o cache" e "contexto que vai para o
modelo" é deliberada e frágil: se o histórico entrar na chave de lookup, cada
conversa passa a ter chave própria, duas perguntas idênticas em conversas
diferentes deixam de casar, e o cache nunca mais acerta — sem erro nenhum,
só custo subindo.

Era o risco número um da Fase 4, porque antes o histórico ficava embutido no
mesmo string do prompt.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import Interaction, InteractionResponse
from app.services.integracoes.ai_providers import StreamToken
from app.services.orquestrador_stream_service import OrquestradorStreamService

pytestmark = pytest.mark.asyncio


class ProviderFake:
    async def complete(self, model_id, prompt, **kwargs):
        raise NotImplementedError

    async def stream(self, model_id, prompt, **kwargs):
        yield StreamToken(delta="resposta")
        yield StreamToken(delta="", done=True, tokens_in=10, tokens_out=5)


@pytest.fixture(autouse=True)
def sem_dependencias(monkeypatch):
    async def _triagem(*a, **k):
        return {"mode": "QUICK_SEARCH", "confidence": 0.99}

    async def _nada(*a, **k):
        return None

    monkeypatch.setattr("app.services.orquestrador_shared.triage", _triagem)
    monkeypatch.setattr("app.services.cache_service.get_json", _nada)
    monkeypatch.setattr("app.services.cache_service.set_json", _nada)


async def _gravar_troca(db, conv, dono, pergunta, resposta):
    interaction = Interaction(
        conversation_id=conv.id,
        user_id=dono.id,
        feature="ORQUESTRADOR",
        mode="QUICK_SEARCH",
        prompt_text=pergunta,
        status="completed",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db.add(interaction)
    await db.flush()
    db.add(InteractionResponse(
        interaction_id=interaction.id,
        model_used="sonar-pro",
        response_text=resposta,
    ))
    await db.flush()


async def test_lookup_do_cache_usa_a_pergunta_atual_sem_historico(
    db, db_conn, user, conversation_factory, model_pricing_factory, monkeypatch
):
    await model_pricing_factory("sonar-pro", provider_type="perplexity")
    conv = await conversation_factory(user)
    await _gravar_troca(db, conv, user, "PERGUNTA ANTIGA sobre cefaleia", "RESPOSTA ANTIGA")

    capturado = {}

    async def _espiao_cache(db_, mode, prompt):
        capturado["prompt"] = prompt
        return None, "", []

    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.get_cached_response", _espiao_cache
    )
    # Mira no MODULO DO SERVICO, nao em ai_providers: o serviço importou o
    # nome direto (`from ... import get_provider_by_type`), entao a referencia
    # ja esta ligada e patchar a origem nao surte efeito.
    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.get_provider_by_type",
        lambda _t: ProviderFake(),
    )

    factory = async_sessionmaker(bind=db_conn, expire_on_commit=False)
    servico = OrquestradorStreamService(factory, user.id)
    _ = [f async for f in servico.stream(prompt="qual a dose?", conversation_id=conv.id)]

    chave = capturado["prompt"]
    assert chave == "qual a dose?"
    assert "PERGUNTA ANTIGA" not in chave, "histórico contaminou a chave do cache"
    assert "RESPOSTA ANTIGA" not in chave


async def test_mesma_pergunta_em_conversas_diferentes_gera_a_mesma_chave(
    db, db_conn, user, conversation_factory, model_pricing_factory, monkeypatch
):
    """
    É o ponto do cache: duas conversas distintas perguntando a mesma coisa
    precisam casar. Com histórico embutido na chave, nunca casariam.
    """
    await model_pricing_factory("sonar-pro", provider_type="perplexity")
    conv_a = await conversation_factory(user, title="A")
    conv_b = await conversation_factory(user, title="B")
    await _gravar_troca(db, conv_a, user, "contexto totalmente diferente A", "resposta A")
    await _gravar_troca(db, conv_b, user, "outro contexto completamente diverso B", "resposta B")

    chaves = []

    async def _espiao_cache(db_, mode, prompt):
        chaves.append(prompt)
        return None, "", []

    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.get_cached_response", _espiao_cache
    )
    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.get_provider_by_type",
        lambda _t: ProviderFake(),
    )

    factory = async_sessionmaker(bind=db_conn, expire_on_commit=False)
    servico = OrquestradorStreamService(factory, user.id)

    for conv in (conv_a, conv_b):
        _ = [f async for f in servico.stream(prompt="qual a dose de dipirona?", conversation_id=conv.id)]

    assert len(chaves) == 2
    assert chaves[0] == chaves[1] == "qual a dose de dipirona?"


async def test_modelo_recebe_o_historico_mesmo_com_a_chave_de_cache_limpa(
    db, db_conn, user, conversation_factory, model_pricing_factory, monkeypatch
):
    """A outra metade: separar a chave não pode significar perder o contexto."""
    await model_pricing_factory("sonar-pro", provider_type="perplexity")
    conv = await conversation_factory(user)
    await _gravar_troca(db, conv, user, "PERGUNTA ANTIGA sobre cefaleia", "RESPOSTA ANTIGA")

    recebido = {}

    class ProviderEspiao(ProviderFake):
        async def stream(self, model_id, prompt, **kwargs):
            recebido["prompt"] = prompt
            recebido["history"] = kwargs.get("history")
            yield StreamToken(delta="ok")
            yield StreamToken(delta="", done=True, tokens_in=1, tokens_out=1)

    async def _sem_cache(*a, **k):
        return None, "", []

    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.get_cached_response", _sem_cache
    )
    monkeypatch.setattr(
        "app.services.orquestrador_stream_service.get_provider_by_type",
        lambda _t: ProviderEspiao(),
    )

    factory = async_sessionmaker(bind=db_conn, expire_on_commit=False)
    servico = OrquestradorStreamService(factory, user.id)
    _ = [f async for f in servico.stream(prompt="e agora?", conversation_id=conv.id)]

    assert recebido["prompt"] == "e agora?"
    conteudo = " ".join(m["content"] for m in recebido["history"])
    assert "PERGUNTA ANTIGA" in conteudo
    assert "RESPOSTA ANTIGA" in conteudo
