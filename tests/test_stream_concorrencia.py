"""
O stream não segura conexão de banco enquanto o modelo responde.

O QUE ISTO VEIO CONSERTAR (itens 18 e 19 da varredura de 2026-09-18)
Cada `/orquestrador/stream` prendia DUAS conexões do início ao fim: a da sessão
da requisição (o FastAPI só encerra `get_db` depois de enviar o corpo, e o corpo
é um stream de até um minuto) e a do serviço, que dava `flush` antes do modelo e
só commitava depois. Com pool de 30+10, cerca de 20 respostas simultâneas
esgotavam o banco — e daí em diante TODA requisição autenticada esperava 30 s e
falhava.

E havia um travamento: `check_limit` gravava (usuário novo, ou virada de semana)
sem commit na sessão da requisição, e o `record_cost` do serviço esperava essa
linha — que só era solta quando o próprio stream terminasse.

POR QUE CONEXÕES REAIS
No harness normal tudo divide UMA conexão: duas sessões nunca disputam conexão
nem linha, e um teste de concorrência ali passa sem provar nada. Aqui o pool é
de verdade, com DUAS conexões (`fabrica_com_conexoes_reais`).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app
from app.models.models import Interaction, ModelPricing, User, UserWeeklyUsage
from app.services import pricing
from app.services.integracoes import ai_providers
from app.services.integracoes.ai_providers import StreamToken
from app.services.orquestrador_stream_service import OrquestradorStreamService
from tests.conftest import auth_headers
from tests.test_orquestrador_stream import (  # noqa: F401 — fixture autouse reusada
    parse_sse,
    sem_dependencias_externas,
)

STREAMS = 6  # o triplo do pool


class ProviderComBarreira:
    """Só responde quando TODOS os streams chegaram até ele.

    É o que torna o teste determinístico. Com conexão presa durante o modelo,
    só dois streams (o tamanho do pool) alcançam o provedor; os outros quatro
    ficam esperando conexão, a barreira nunca fecha e o pool estoura o timeout.
    """

    def __init__(self, esperados: int, pool):
        self.esperados = esperados
        self.pool = pool
        self.chegaram = 0
        self.todos = asyncio.Event()
        self.conexoes_presas_durante_o_modelo: list[int] = []

    async def complete(self, *_a, **_kw):
        raise NotImplementedError

    async def stream(self, model_id, prompt, **_kw):
        self.chegaram += 1
        if self.chegaram >= self.esperados:
            self.todos.set()
        await asyncio.wait_for(self.todos.wait(), timeout=10)
        self.conexoes_presas_durante_o_modelo.append(self.pool.checkedout())
        yield StreamToken(delta="resposta")
        yield StreamToken(delta="", done=True, tokens_in=10, tokens_out=5)


@pytest.fixture
async def cenario_real(fabrica_com_conexoes_reais):
    """Usuário e modelo COMITADOS de verdade — outra conexão precisa enxergá-los."""
    pricing._pricing_cache.clear()
    async with fabrica_com_conexoes_reais() as db:
        user = User(email="concorrencia@example.com", role="beta_user", status=True,
                    onboarding_complete=True, name="Dra. Concorrência")
        db.add(user)
        db.add(ModelPricing(
            model_id="sonar-pro", provider="perplexity", provider_type="perplexity",
            display_name="sonar-pro", input_per_million=Decimal("3"),
            output_per_million=Decimal("15"), status=True,
        ))
        await db.commit()
        await db.refresh(user)
    yield user
    pricing._pricing_cache.clear()


async def test_seis_streams_num_pool_de_duas_conexoes_terminam_todos(
    fabrica_com_conexoes_reais, cenario_real, monkeypatch
):
    pool = fabrica_com_conexoes_reais.kw["bind"].sync_engine.pool
    provider = ProviderComBarreira(STREAMS, pool)
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", provider)

    async def um_stream(i: int):
        servico = OrquestradorStreamService(fabrica_com_conexoes_reais, cenario_real.id)
        frames = [f async for f in servico.stream(prompt=f"pergunta clínica número {i}", mode="QUICK_SEARCH")]
        return [nome for nome, _ in parse_sse(frames)]

    resultados = await asyncio.wait_for(
        asyncio.gather(*(um_stream(i) for i in range(STREAMS))), timeout=30
    )

    for eventos in resultados:
        assert eventos[-1] == "done", f"stream não terminou: {eventos}"
        assert "error" not in eventos
    assert provider.conexoes_presas_durante_o_modelo == [0] * STREAMS, (
        "Havia conexão de banco presa enquanto o modelo respondia: "
        f"{provider.conexoes_presas_durante_o_modelo}"
    )

    async with fabrica_com_conexoes_reais() as db:
        from sqlalchemy import func, select

        concluidas = await db.scalar(
            select(func.count()).select_from(Interaction).where(Interaction.status == "completed")
        )
        custo = await db.scalar(
            select(UserWeeklyUsage.total_cost_usd).where(UserWeeklyUsage.user_id == cenario_real.id)
        )
    assert concluidas == STREAMS
    # Seis respostas terminando juntas: com o ler-somar-gravar de antes, somas se
    # perdiam. 10 tokens a $3/M + 5 a $15/M = $0,000105 por resposta.
    assert custo == Decimal("0.000105") * STREAMS


async def test_virada_de_semana_nao_trava_o_stream_via_http(
    fabrica_com_conexoes_reais, cenario_real, monkeypatch
):
    """O travamento do item 19, pela rota de verdade.

    Usuário beta com a semana vencida: `check_limit` zerava a semana SEM commit na
    sessão da requisição, e o `record_cost` do stream esperava o bloqueio dessa
    linha — que só se soltava quando o stream acabasse. O texto aparecia inteiro
    e a resposta travava antes do `text_done`.
    """
    async with fabrica_com_conexoes_reais() as db:
        db.add(UserWeeklyUsage(
            user_id=cenario_real.id,
            week_start=datetime.now(UTC) - timedelta(days=8),
            total_cost_usd=Decimal("4.99"),
        ))
        await db.commit()

    pool = fabrica_com_conexoes_reais.kw["bind"].sync_engine.pool
    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "perplexity", ProviderComBarreira(1, pool))
    monkeypatch.setattr(
        "app.api.v1.endpoints.orquestrador.async_session_factory", fabrica_com_conexoes_reais
    )

    async def _get_db_real():
        # Espelha `app.core.database.get_db`: commit no fim, DEPOIS do corpo.
        async with fabrica_com_conexoes_reais() as sessao:
            yield sessao
            await sessao.commit()

    app.dependency_overrides[get_db] = _get_db_real
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as cliente:
            resp = await asyncio.wait_for(
                cliente.post(
                    "/api/v1/orquestrador/stream",
                    json={"prompt": "qual a dose de amoxicilina?", "mode": "QUICK_SEARCH"},
                    headers=auth_headers(cenario_real),
                ),
                timeout=5,
            )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "event: text_done" in resp.text, "o stream travou antes do text_done"
    assert "event: done" in resp.text

    async with fabrica_com_conexoes_reais() as db:
        from sqlalchemy import select

        uso = (
            await db.execute(select(UserWeeklyUsage).where(UserWeeklyUsage.user_id == cenario_real.id))
        ).scalar_one()
    assert uso.total_cost_usd == Decimal("0.000105"), "a semana vencida não foi zerada"
    assert (datetime.now(UTC) - uso.week_start).total_seconds() < 60
