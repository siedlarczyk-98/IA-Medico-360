"""
O DATA_OCEAN grava histórico como qualquer outro modo — e o que ele grava
quando falha precisa ser distinguível do que grava quando dá certo.

POR QUE ESTE ARQUIVO EXISTE
---------------------------
Surgiu de uma suspeita de que o modo "não estaria persistindo as respostas nas
conversas". A persistência estava íntegra: o DATA_OCEAN percorre o mesmo caminho
dos demais modos (`ensure_conversation` → `Interaction` → `InteractionResponse`),
sem nenhum desvio. `tests/test_data_ocean.py` cobria registro, ausência de
fallback/cache/triagem e custo de ferramentas — mas nada afirmava que uma
interação vira histórico recuperável, e foi essa lacuna que deixou a dúvida de
pé.

O que provavelmente produziu o sintoma é o outro teste daqui: o modo **não tem
fallback por decisão** (cair para outro modelo devolveria números inventados com
cara de consulta ao DATASUS), então quando o fluxo agêntico falha o que se grava
é a mensagem genérica de erro. Ela era persistida e reexibida com a mesma
aparência de uma resposta legítima — e quem reabria a conversa lia "não salvou"
onde o certo era "a consulta falhou". Daí o `is_fallback` viajar até a interface.

O modo é lento (fluxo agêntico de dezenas de segundos), o que o expõe mais que
os outros a um abort antes do commit. Isso não é defeito de lógica e não é o que
estes testes cobrem.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.models import Interaction, InteractionResponse
from app.services.integracoes import ai_providers
from app.services.integracoes.ai_providers import StreamToken
from app.services.orquestrador_stream_service import OrquestradorStreamService

from tests.test_orquestrador_stream import (  # noqa: F401 — fixtures reusadas
    parse_sse,
    sem_dependencias_externas,
)

TEXTO = "Em 2025 o DATASUS registrou X internações por dengue no estado."


class MaritacaFake:
    """Emite deltas como o provider real: o Maritaca fatia o `complete()`."""

    async def complete(self, model_id, prompt, **kwargs):
        raise NotImplementedError

    async def stream(self, model_id, prompt, **kwargs):
        for pedaco in (TEXTO[:30], TEXTO[30:]):
            yield StreamToken(delta=pedaco)
        yield StreamToken(
            delta="", done=True, tokens_in=90, tokens_out=40,
            tool_usage={"data_ocean_gb_processed": 1},
        )


class MaritacaQueFalha:
    """O fluxo agêntico estourando — timeout é o caso real em produção."""

    async def complete(self, model_id, prompt, **kwargs):
        raise TimeoutError("fluxo agêntico excedeu o tempo")

    async def stream(self, model_id, prompt, **kwargs):
        raise TimeoutError("fluxo agêntico excedeu o tempo")
        yield  # pragma: no cover — torna a função um gerador


@pytest.fixture
def servico(db_conn, user):
    factory = async_sessionmaker(bind=db_conn, expire_on_commit=False)
    return OrquestradorStreamService(factory, user.id)


async def _rodar(servico, provider, monkeypatch, model_pricing_factory):
    await model_pricing_factory(model_id="sabia-4-thinking", provider_type="maritaca")
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "maritaca", provider)
    frames = [
        f async for f in servico.stream(prompt="Dengue no meu estado", mode="DATA_OCEAN")
    ]
    return parse_sse(frames)


async def _resposta_gravada(db, user):
    """A `InteractionResponse` do DATA_OCEAN gravada para este usuário."""
    interacao = (await db.execute(
        select(Interaction).where(
            Interaction.user_id == user.id,
            Interaction.mode == "DATA_OCEAN",
        )
    )).scalars().first()
    assert interacao is not None, "a Interaction do DATA_OCEAN não foi gravada"

    resposta = (await db.execute(
        select(InteractionResponse).where(
            InteractionResponse.interaction_id == interacao.id
        )
    )).scalars().first()
    assert resposta is not None, "a InteractionResponse não foi gravada"
    return interacao, resposta


async def test_resposta_bem_sucedida_vira_historico(
    servico, db, user, monkeypatch, model_pricing_factory
):
    """A afirmação que faltava: a consulta vira linha recuperável no banco."""
    await _rodar(servico, MaritacaFake(), monkeypatch, model_pricing_factory)

    interacao, resposta = await _resposta_gravada(db, user)

    assert interacao.feature == "ORQUESTRADOR"
    # O filtro da lista de conversas esconde `feature == "AGREGADOR"`; o modo
    # vive em `mode`, então o DATA_OCEAN nunca cai nesse filtro.
    assert interacao.mode == "DATA_OCEAN"
    assert resposta.response_text == TEXTO
    assert resposta.is_fallback is False


async def test_a_conversa_e_criada_e_devolvida_no_sse(
    servico, monkeypatch, model_pricing_factory
):
    """Sem `conversation_id` no `done`, o front abriria uma conversa nova na
    mensagem seguinte e a anterior ficaria órfã na lista."""
    eventos = await _rodar(servico, MaritacaFake(), monkeypatch, model_pricing_factory)

    done = next(dados for nome, dados in eventos if nome == "done")
    assert done["conversation_id"]
    assert done["mode"] == "DATA_OCEAN"


async def test_falha_grava_a_mensagem_generica_marcada_como_fallback(
    servico, db, user, monkeypatch, model_pricing_factory
):
    """
    O caso que se parece com "não persistiu".

    O DATA_OCEAN não tem fallback, então a falha vira a frase genérica de erro.
    Ela É gravada — o que faltava era `is_fallback` chegar à interface para que
    o médico distinga isso de uma consulta que deu certo.
    """
    await _rodar(servico, MaritacaQueFalha(), monkeypatch, model_pricing_factory)

    _, resposta = await _resposta_gravada(db, user)

    assert resposta.is_fallback is True
    assert "não foi possível processar" in resposta.response_text


async def test_o_sse_anuncia_o_fallback(
    servico, monkeypatch, model_pricing_factory
):
    """Ao vivo, não só ao reabrir: o aviso precisa sair no mesmo turno."""
    eventos = await _rodar(servico, MaritacaQueFalha(), monkeypatch, model_pricing_factory)

    done = next(dados for nome, dados in eventos if nome == "done")
    assert done["is_fallback"] is True


async def test_nao_cai_para_outro_modelo(
    servico, db, user, monkeypatch, model_pricing_factory
):
    """
    A invariante do modo: falhar visivelmente é melhor que responder de memória.

    Se um dia alguém adicionar o DATA_OCEAN a `FALLBACK_MODELS`, a resposta
    passaria a vir de um modelo que NÃO consulta as bases brasileiras — fluente,
    plausível e possivelmente com números inventados. Este teste quebra antes.
    """
    await _rodar(servico, MaritacaQueFalha(), monkeypatch, model_pricing_factory)

    _, resposta = await _resposta_gravada(db, user)

    assert resposta.model_used == "sabia-4-thinking"
