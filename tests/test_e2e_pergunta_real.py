"""
E2E do fluxo principal, com CHAMADA REAL aos provedores.

O médico faz uma pergunta e recebe uma resposta. É o caminho que sustenta o
produto inteiro, e é o único teste do projeto que o exercita de ponta a ponta
contra as APIs de verdade: app real, banco real, request HTTP real, LLM real.

POR QUE ISTO EXISTE, TENDO 936 TESTES UNITÁRIOS
Os unitários testam as peças. Este testa a montagem — e a diferença não é
teórica: em 2026-09-08 três bugs distintos passaram pela suíte inteira e só
apareceram lendo o código (exame anexado indo para modelo sem visão, imagem
perdida no fallback, `record_cost` ausente no `/query`). Um teste que roda o
fluxo de verdade pega a classe de erro que nenhum mock pega: contrato do
provedor mudou, campo renomeado, migration que não aplica, serialização que
quebra só com dado real.

CUSTA DINHEIRO E NÃO É DETERMINÍSTICO
Cada execução gasta cota real dos provedores, e a resposta do modelo varia.
Por isso:

  - Todos os testes são marcados com `@pytest.mark.rede_real`, que desarma o
    guard de rede do `conftest`.
  - **Não rodam por padrão.** Exigem `E2E_REDE_REAL=1` no ambiente, senão são
    pulados. O CI não tem chave de API nenhuma, então lá eles simplesmente não
    rodam — e não quebram o build.
  - As asserções verificam ESTRUTURA e EFEITO (status, campos, o que foi
    gravado no banco), nunca o TEOR da resposta. Um teste que exigisse o modelo
    dizer certa palavra falharia por variação normal do modelo, e alguém
    aprenderia a ignorá-lo.

COMO RODAR

    E2E_REDE_REAL=1 pytest tests/test_e2e_pergunta_real.py -v

Precisa das chaves reais no ambiente (as mesmas do `.env`). Vale rodar antes de
um deploy, não a cada commit.
"""

import os

import pytest
from sqlalchemy import select

from app.models.models import Interaction, InteractionResponse
from tests.conftest import auth_headers

# Dois portões, e os dois são necessários:
# `rede_real` desarma o bloqueio de rede; a variável de ambiente impede que uma
# execução distraída de `pytest` gaste cota real sem ninguém ter pedido.
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.rede_real,
    pytest.mark.skipif(
        os.environ.get("E2E_REDE_REAL") != "1",
        reason="E2E com chamada real: exige E2E_REDE_REAL=1 (gasta cota dos provedores)",
    ),
]


# Pergunta genérica de propósito: sem dado de paciente, para não mandar nada
# parecido com PII a um provedor externo num teste, e curta o bastante para a
# resposta não custar caro.
PERGUNTA = "Qual a dose usual de amoxicilina para sinusite bacteriana em adultos?"


async def test_pergunta_de_ponta_a_ponta_devolve_resposta_e_grava_no_banco(
    client, user, db, model_pricing_factory
):
    """O fluxo inteiro: HTTP → DLP → triagem → provedor → persistência.

    As asserções são sobre estrutura e efeito. O TEOR da resposta não é
    verificado: o modelo varia, e um teste que dependesse da redação exata
    falharia sozinho até alguém aprender a ignorá-lo.
    """
    await model_pricing_factory(
        model_id="sonar-pro", provider_type="perplexity",
        input_per_million="1.00", output_per_million="1.00",
    )

    resp = await client.post(
        "/api/v1/orquestrador/query",
        json={"prompt": PERGUNTA, "mode": "QUICK_SEARCH"},
        headers=auth_headers(user),
        timeout=90,
    )

    assert resp.status_code == 200, resp.text
    corpo = resp.json()

    # A resposta chegou e não está vazia.
    assert corpo.get("response_text"), "o médico receberia uma resposta vazia"
    assert corpo.get("conversation_id")
    assert corpo.get("interaction_id")

    # E foi gravada — sem isto a conversa some ao recarregar a tela.
    interacoes = (await db.execute(
        select(Interaction).where(Interaction.user_id == user.id)
    )).scalars().all()
    assert len(interacoes) == 1
    assert interacoes[0].mode == "QUICK_SEARCH"
    assert interacoes[0].completed_at is not None

    respostas = (await db.execute(
        select(InteractionResponse).where(
            InteractionResponse.interaction_id == interacoes[0].id
        )
    )).scalars().all()
    assert len(respostas) == 1
    assert respostas[0].response_text


async def test_o_custo_real_e_contabilizado(client, user, db, model_pricing_factory):
    """O bug que a revisão de hoje encontrou: `check_limit` lia um contador que
    o `/query` nunca incrementava.

    Um mock não pegaria isto — precisa de `tokens_in`/`tokens_out` de verdade,
    vindos do provedor.
    """
    from app.models.models import UserWeeklyUsage

    await model_pricing_factory(
        model_id="sonar-pro", provider_type="perplexity",
        input_per_million="1.00", output_per_million="1.00",
    )

    await client.post(
        "/api/v1/orquestrador/query",
        json={"prompt": PERGUNTA, "mode": "QUICK_SEARCH"},
        headers=auth_headers(user),
        timeout=90,
    )

    interacao = (await db.execute(
        select(Interaction).where(Interaction.user_id == user.id)
    )).scalar_one()
    assert interacao.token_cost_usd > 0, (
        "custo zero com chamada real significa que os tokens não voltaram"
    )

    uso = (await db.execute(
        select(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user.id)
    )).scalar_one_or_none()
    assert uso is not None, "o custo não entrou no medidor semanal"
    assert uso.total_cost_usd > 0


async def test_streaming_entrega_o_texto_em_pedacos(client, user, model_pricing_factory):
    """QUICK_SEARCH passou a streamar de verdade hoje (`stream_options`).

    Contra a API real, este teste prova o que os testes com fake não podem: que
    a Perplexity de fato aceita o parâmetro e devolve os eventos esperados.
    """
    await model_pricing_factory(
        model_id="sonar-pro", provider_type="perplexity",
        input_per_million="1.00", output_per_million="1.00",
    )

    eventos: list[str] = []
    async with client.stream(
        "POST",
        "/api/v1/orquestrador/stream",
        json={"prompt": PERGUNTA, "mode": "QUICK_SEARCH"},
        headers=auth_headers(user),
        timeout=90,
    ) as resp:
        assert resp.status_code == 200
        async for linha in resp.aiter_lines():
            if linha.startswith("event: "):
                eventos.append(linha[7:].strip())

    assert "token" in eventos, "nenhum token foi emitido — o stream não streamou"
    assert eventos.count("token") > 1, (
        "só um evento de token: a resposta veio inteira de uma vez, "
        "o que era o comportamento antigo"
    )
    assert "done" in eventos


async def test_a_triagem_real_classifica_a_pergunta(client, user, db, model_pricing_factory):
    """Sem `mode` explícito, quem escolhe é a triagem — um LLM.

    Verifica que ela devolve um modo VÁLIDO, não um modo específico: exigir
    "QUICK_SEARCH" aqui seria testar o julgamento do modelo, que muda.
    """
    from app.services.orquestrador_modes import VALID_MODES

    for mid, ptype in (("sonar-pro", "perplexity"), ("claude-sonnet-4-6", "anthropic")):
        await model_pricing_factory(
            model_id=mid, provider_type=ptype,
            input_per_million="1.00", output_per_million="1.00",
        )

    resp = await client.post(
        "/api/v1/orquestrador/query",
        json={"prompt": PERGUNTA},
        headers=auth_headers(user),
        timeout=90,
    )

    assert resp.status_code == 200, resp.text
    interacao = (await db.execute(
        select(Interaction).where(Interaction.user_id == user.id)
    )).scalar_one()
    assert interacao.mode in VALID_MODES
    assert interacao.triage_confidence is not None
