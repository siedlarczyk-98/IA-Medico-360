"""
Resiliência do Agregador — pelo caminho que ESTÁ EM USO.

REESCRITO em 2026-09-21. Estes seis testes exercitavam `AgregadorService.query`,
o método da rota `/agregador/query` — que não tinha NENHUM chamador em todo o
monorepo. Enquanto isso o `/agregador/stream`, que é o caminho de verdade, não
tinha um único teste de comportamento: a falha de um modelo derrubar os outros, o
custo do modelo que falhou, o prompt gravado sem sanitizar — nada disso era
conferido onde importava. É o padrão recorrente deste projeto: o teste confirmava
o fluxo imaginado, não o real.

A rota e o método mortos foram removidos; as mesmas seis propriedades (RN-AGR-001,
contabilização de custo e DLP) agora são conferidas pela rota, via HTTP.
"""

import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.models import Interaction, InteractionResponse, UserWeeklyUsage
from app.services.integracoes import ai_providers
from app.services.integracoes.ai_providers import StreamToken
from tests.conftest import auth_headers


class ProviderQueResponde:
    def __init__(self, texto="resposta ok", tokens_in=1000, tokens_out=500):
        self.texto, self.tokens_in, self.tokens_out = texto, tokens_in, tokens_out

    async def complete(self, model_id, prompt, **kwargs):
        raise NotImplementedError

    async def stream(self, model_id, prompt, **kwargs):
        yield StreamToken(delta=f"{self.texto} ")
        yield StreamToken(delta=f"({model_id})")
        yield StreamToken(delta="", done=True, tokens_in=self.tokens_in, tokens_out=self.tokens_out)


class ProviderQueFalha:
    def __init__(self, erro="provedor fora do ar"):
        self.erro = erro

    async def complete(self, model_id, prompt, **kwargs):
        raise NotImplementedError

    async def stream(self, model_id, prompt, **kwargs):
        raise RuntimeError(self.erro)
        yield  # pragma: no cover — torna a função um gerador


@pytest.fixture(autouse=True)
def sem_enriquecimento(monkeypatch):
    """Desliga o pós-processamento best-effort (especialidade, medicamentos, PubMed)."""
    async def _especialidade(_texto):
        return {"specialty": None, "topic": None}

    async def _medicamentos(*args, **kwargs):
        return []

    async def _sem_pubmed(*args, **kwargs):
        from app.services.integracoes.pubmed_service import ValidationResult

        return ValidationResult(confidence_score=0.0, fallback=True)

    monkeypatch.setattr("app.services.agregador_service.detect_specialty_and_topic", _especialidade)
    monkeypatch.setattr("app.services.agregador_service.extract_from_interaction", _medicamentos)
    monkeypatch.setattr("app.services.agregador_service.validate_with_pubmed", _sem_pubmed, raising=False)


@pytest.fixture
def registra_providers(monkeypatch):
    """Substitui os providers reais por fakes, por tipo."""
    def _registra(**por_tipo):
        for tipo, fake in por_tipo.items():
            monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, tipo, fake)

    return _registra


def _eventos(corpo: str) -> list[tuple[str, dict]]:
    """Frames SSE → [(evento, dados)]."""
    eventos = []
    for frame in corpo.replace("\r\n", "\n").split("\n\n"):
        nome, dados = None, None
        for linha in frame.split("\n"):
            if linha.startswith("event:"):
                nome = linha[6:].strip()
            elif linha.startswith("data:"):
                dados = json.loads(linha[5:].strip())
        if nome and dados is not None:
            eventos.append((nome, dados))
    return eventos


async def _consultar(client, user, prompt, modelos):
    resp = await client.post(
        "/api/v1/agregador/stream",
        json={"prompt": prompt, "models": modelos},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    return _eventos(resp.text)


def _texto_de(eventos, modelo) -> str:
    return "".join(d["delta"] for e, d in eventos if e == "delta" and d["model_id"] == modelo)


# ── RN-AGR-001 ───────────────────────────────────────────────────────────

async def test_falha_de_um_modelo_nao_derruba_os_demais(
    client, user, model_pricing_factory, registra_providers
):
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    await model_pricing_factory(model_id="modelo-ruim", provider_type="openai")
    registra_providers(anthropic=ProviderQueResponde(), openai=ProviderQueFalha("503 do provedor"))

    eventos = await _consultar(
        client, user, "Conduta em pneumonia adquirida na comunidade?", ["modelo-bom", "modelo-ruim"]
    )

    assert _texto_de(eventos, "modelo-bom") == "resposta ok (modelo-bom)"
    erros = [d for e, d in eventos if e == "error"]
    assert [d["model_id"] for d in erros] == ["modelo-ruim"]
    # O cliente recebe uma frase fixa; o texto cru do provedor não sai do servidor.
    assert "503" not in json.dumps(erros)
    assert eventos[-1][0] == "done"


async def test_todos_os_modelos_falhando_ainda_encerra_o_stream(
    client, user, model_pricing_factory, registra_providers
):
    await model_pricing_factory(model_id="m1", provider_type="anthropic")
    await model_pricing_factory(model_id="m2", provider_type="openai")
    registra_providers(anthropic=ProviderQueFalha(), openai=ProviderQueFalha())

    eventos = await _consultar(client, user, "Pergunta qualquer", ["m1", "m2"])

    assert sorted(d["model_id"] for e, d in eventos if e == "error") == ["m1", "m2"]
    assert eventos[-1][0] == "done", "com tudo falhando o stream ainda precisa terminar limpo"


async def test_erro_de_um_modelo_e_persistido(
    client, db, user, model_pricing_factory, registra_providers
):
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    await model_pricing_factory(model_id="modelo-ruim", provider_type="openai")
    registra_providers(anthropic=ProviderQueResponde(), openai=ProviderQueFalha("timeout de conexão"))

    await _consultar(client, user, "Pergunta", ["modelo-bom", "modelo-ruim"])

    por_modelo = {r.model_used: r for r in (await db.execute(select(InteractionResponse))).scalars()}
    # O diagnóstico fica no banco, mesmo não indo para a tela.
    assert "timeout" in por_modelo["modelo-ruim"].error_message
    assert por_modelo["modelo-bom"].error_message is None
    assert por_modelo["modelo-bom"].response_text == "resposta ok (modelo-bom)"


# ── Contabilização de custo ──────────────────────────────────────────────

async def test_so_cobra_pelos_modelos_que_responderam(
    client, db, user, model_pricing_factory, registra_providers
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

    await _consultar(client, user, "Pergunta", ["modelo-bom", "modelo-ruim"])

    uso = (
        await db.execute(
            select(UserWeeklyUsage)
            .where(UserWeeklyUsage.user_id == user.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    # 1M tokens de entrada a 10 + 1M de saída a 30 = 40 USD, só do modelo que respondeu.
    assert uso.total_cost_usd == Decimal("40.000000")


async def test_modelo_desconhecido_e_ignorado_sem_quebrar(
    client, user, model_pricing_factory, registra_providers
):
    """Model id que não está na tabela de preços não pode derrubar a consulta."""
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    registra_providers(anthropic=ProviderQueResponde())

    eventos = await _consultar(client, user, "Pergunta", ["modelo-bom", "modelo-que-nao-existe"])

    assert {d["model_id"] for e, d in eventos if e in ("delta", "complete", "error")} == {"modelo-bom"}
    assert eventos[-1][0] == "done"


# ── DLP no caminho do Agregador ──────────────────────────────────────────

async def test_prompt_persistido_e_o_enviado_ao_modelo_vao_sanitizados(
    client, db, user, model_pricing_factory, monkeypatch
):
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    recebidos: list[str] = []

    class ProviderEspiao(ProviderQueResponde):
        async def stream(self, model_id, prompt, **kwargs):
            recebidos.append(prompt)
            async for token in super().stream(model_id, prompt, **kwargs):
                yield token

    monkeypatch.setitem(ai_providers.PROVIDER_TYPE_REGISTRY, "anthropic", ProviderEspiao())

    await _consultar(
        client, user, "Paciente João da Silva, CPF 123.456.789-00, com febre", ["modelo-bom"]
    )

    interacao = (await db.execute(select(Interaction))).scalar_one()
    for texto in (interacao.prompt_text, recebidos[0]):
        assert "123.456.789-00" not in texto
        assert "João da Silva" not in texto


async def test_resposta_do_modelo_tambem_e_gravada_mascarada(
    client, db, user, model_pricing_factory, registra_providers
):
    """
    Achado de 2026-09-21: só o `query()` morto mascarava a RESPOSTA antes de gravar.
    O caminho em uso gravava o texto cru — um modelo que repete o CPF do paciente na
    resposta deixava o dado no histórico, mesmo com o prompt mascarado.
    """
    await model_pricing_factory(model_id="modelo-bom", provider_type="anthropic")
    registra_providers(
        anthropic=ProviderQueResponde(texto="Para o paciente de CPF 123.456.789-00, a conduta é")
    )

    await _consultar(client, user, "Qual a conduta?", ["modelo-bom"])

    gravada = (await db.execute(select(InteractionResponse.response_text))).scalar_one()
    assert "123.456.789-00" not in gravada
    assert "a conduta é" in gravada, "o mascaramento não pode comer o resto da resposta"
