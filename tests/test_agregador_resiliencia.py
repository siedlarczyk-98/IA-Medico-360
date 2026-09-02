"""
Resiliência do Agregador — RN-AGR-001 (item 1.3 do plano de prontidão).

A regra está escrita no código desde sempre ("Se um modelo falhar, não impacta
os demais") mas nunca teve teste. É o comportamento que sustenta a proposta do
Agregador: consultar vários modelos em paralelo e mostrar o que cada um respondeu.

Nenhum teste aqui toca a rede — os providers são substituídos por fakes.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.models import InteractionResponse, UserWeeklyUsage
from app.schemas.agregador import AgregadorRequest
from app.services.agregador_service import AgregadorService
from app.services.integracoes import ai_providers
from app.services.integracoes.ai_providers import ProviderResponse


class ProviderQueResponde:
    def __init__(self, texto="resposta ok", tokens_in=1000, tokens_out=500):
        self.texto, self.tokens_in, self.tokens_out = texto, tokens_in, tokens_out

    async def complete(self, model_id, prompt, **kwargs):
        return ProviderResponse(
            text=f"{self.texto} ({model_id})",
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
        )

    async def stream(self, model_id, prompt, **kwargs):
        raise NotImplementedError


class ProviderQueFalha:
    def __init__(self, erro="provedor fora do ar"):
        self.erro = erro

    async def complete(self, model_id, prompt, **kwargs):
        raise RuntimeError(self.erro)

    async def stream(self, model_id, prompt, **kwargs):
        raise NotImplementedError


@pytest.fixture(autouse=True)
def sem_enriquecimento(monkeypatch):
    """
    Desliga o pós-processamento best-effort (especialidade, medicamentos, PubMed).
    Ele já é tolerante a falha no código; aqui só evita ruído e lentidão.
    """
    async def _especialidade(_texto):
        return {"specialty": None, "topic": None}

    async def _medicamentos(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.agregador_service.detect_specialty_and_topic", _especialidade)
    monkeypatch.setattr("app.services.agregador_service.extract_from_interaction", _medicamentos)


@pytest.fixture
def registra_providers(monkeypatch):
    """Substitui os providers reais por fakes, por tipo."""
    def _registra(**por_tipo):
        for tipo, fake in por_tipo.items():
            monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, tipo, fake)

    return _registra


# ── RN-AGR-001 ───────────────────────────────────────────────────────────

async def test_falha_de_um_modelo_nao_derruba_os_demais(
    db, user, model_pricing_factory, registra_providers
):
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    await model_pricing_factory(model_id="modelo-ruim", provider_type="openai")
    registra_providers(anthropic=ProviderQueResponde(), openai=ProviderQueFalha("503 do provedor"))

    servico = AgregadorService(db, user.id)
    resposta = await servico.query(
        AgregadorRequest(prompt="Conduta em pneumonia adquirida na comunidade?",
                         models=["modelo-bom", "modelo-ruim"])
    )

    por_modelo = {r.model_id: r for r in resposta.responses}
    assert por_modelo["modelo-bom"].response_text, "O modelo saudável deveria ter respondido"
    assert not por_modelo["modelo-bom"].error
    assert "503 do provedor" in por_modelo["modelo-ruim"].error
    assert por_modelo["modelo-ruim"].response_text == ""


async def test_todos_os_modelos_falhando_ainda_devolve_resposta(
    db, user, model_pricing_factory, registra_providers
):
    """Falha total precisa virar erro por modelo, não exceção que perde a interação."""
    await model_pricing_factory(model_id="m1", provider_type="anthropic")
    await model_pricing_factory(model_id="m2", provider_type="openai")
    registra_providers(anthropic=ProviderQueFalha(), openai=ProviderQueFalha())

    resposta = await AgregadorService(db, user.id).query(
        AgregadorRequest(prompt="Pergunta qualquer", models=["m1", "m2"])
    )

    assert len(resposta.responses) == 2
    assert all(r.error for r in resposta.responses)


async def test_erro_de_um_modelo_e_persistido(
    db, user, model_pricing_factory, registra_providers
):
    """O erro precisa ficar registrado, senão não há como investigar depois."""
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    await model_pricing_factory(model_id="modelo-ruim", provider_type="openai")
    registra_providers(anthropic=ProviderQueResponde(), openai=ProviderQueFalha("timeout"))

    await AgregadorService(db, user.id).query(
        AgregadorRequest(prompt="Pergunta", models=["modelo-bom", "modelo-ruim"])
    )

    linhas = (await db.execute(select(InteractionResponse))).scalars().all()
    por_modelo = {r.model_used: r for r in linhas}
    assert por_modelo["modelo-ruim"].error_message
    assert "timeout" in por_modelo["modelo-ruim"].error_message
    assert por_modelo["modelo-bom"].error_message is None


# ── Contabilização de custo ──────────────────────────────────────────────

async def test_so_cobra_pelos_modelos_que_responderam(
    db, user, model_pricing_factory, registra_providers
):
    """Modelo que falhou não pode gerar custo."""
    await model_pricing_factory(
        model_id="modelo-bom", provider_type="anthropic",
        input_per_million="10.00", output_per_million="30.00",
    )
    await model_pricing_factory(model_id="modelo-ruim", provider_type="openai")
    registra_providers(
        anthropic=ProviderQueResponde(tokens_in=1_000_000, tokens_out=1_000_000),
        openai=ProviderQueFalha(),
    )

    await AgregadorService(db, user.id).query(
        AgregadorRequest(prompt="Pergunta", models=["modelo-bom", "modelo-ruim"])
    )

    uso = (await db.execute(select(UserWeeklyUsage).where(UserWeeklyUsage.user_id == user.id))).scalar_one()
    # 1M tokens de entrada a 10 + 1M de saída a 30 = 40 USD, só do modelo que respondeu.
    assert uso.total_cost_usd == Decimal("40.000000")


async def test_modelo_desconhecido_e_ignorado_sem_quebrar(
    db, user, model_pricing_factory, registra_providers
):
    """Model id que não está na tabela de preços não pode derrubar a consulta."""
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    registra_providers(anthropic=ProviderQueResponde())

    resposta = await AgregadorService(db, user.id).query(
        AgregadorRequest(prompt="Pergunta", models=["modelo-bom", "modelo-que-nao-existe"])
    )

    assert [r.model_id for r in resposta.responses] == ["modelo-bom"]


# ── DLP no caminho do Agregador ──────────────────────────────────────────

async def test_prompt_persistido_vai_sanitizado(
    db, user, model_pricing_factory, registra_providers
):
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    registra_providers(anthropic=ProviderQueResponde())

    await AgregadorService(db, user.id).query(
        AgregadorRequest(prompt="Paciente João da Silva, CPF 123.456.789-00, com febre",
                         models=["modelo-bom"])
    )

    from app.models.models import Interaction

    interacao = (await db.execute(select(Interaction))).scalar_one()
    assert "123.456.789-00" not in interacao.prompt_text
    assert "João da Silva" not in interacao.prompt_text
    assert interacao.prompt_sanitized is True
    assert "febre" in interacao.prompt_text
