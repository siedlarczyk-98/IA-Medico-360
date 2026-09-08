"""
Garantia de que nenhum prompt sai para provedor externo sem passar pelo DLP
(item 1.3 do plano de prontidão).

O `DlpEnforcingProvider` é a rede de segurança: mesmo que um serviço futuro
esqueça de chamar `sanitize_prompt`, nada não sanitizado chega à Anthropic,
OpenAI, Google ou Perplexity. Até agora isso era convenção — aqui vira asserção.

RN-SEC-001: nenhuma PII pode sair do backend brasileiro.
"""

import pytest

from app.services.integracoes.ai_providers import (
    PROVIDER_TYPE_REGISTRY,
    DlpEnforcingProvider,
    ProviderResponse,
    StreamToken,
    get_provider_by_type,
)

PROMPT_COM_PII = (
    "João Silva, 45 anos, CPF 123.456.789-00, telefone (11) 99999-0000, "
    "mora na Rua das Flores, 123. Encaminhado pelo Dr. Carlos Santos."
)


class ProviderEspiao:
    """Captura o prompt que chegaria ao provedor externo."""

    def __init__(self):
        self.prompt_recebido: str | None = None

    async def complete(self, model_id, prompt, **kwargs) -> ProviderResponse:
        self.prompt_recebido = prompt
        return ProviderResponse(text="ok", tokens_in=1, tokens_out=1)

    async def stream(self, model_id, prompt, **kwargs):
        self.prompt_recebido = prompt
        yield StreamToken(delta="ok", done=True)


# ── Todo provider registrado sai embrulhado ──────────────────────────────

@pytest.mark.parametrize("provider_type", sorted(PROVIDER_TYPE_REGISTRY))
def test_provider_sempre_vem_com_dlp(provider_type):
    """
    Varre o registry: um provider novo adicionado sem passar por
    `get_provider_by_type` faria este teste falhar.
    """
    provider = get_provider_by_type(provider_type)
    assert isinstance(provider, DlpEnforcingProvider), (
        f"Provider '{provider_type}' não está embrulhado pelo DLP."
    )


def test_provider_desconhecido_falha_alto():
    """Melhor estourar do que devolver algo sem DLP."""
    with pytest.raises(ValueError, match="não suportado"):
        get_provider_by_type("provedor-inexistente")


# ── O embrulho realmente sanitiza ────────────────────────────────────────

async def test_complete_sanitiza_antes_de_enviar():
    espiao = ProviderEspiao()

    await DlpEnforcingProvider(espiao).complete("modelo-x", PROMPT_COM_PII)

    enviado = espiao.prompt_recebido
    assert "123.456.789-00" not in enviado
    assert "99999-0000" not in enviado
    assert "João Silva" not in enviado
    assert "Carlos Santos" not in enviado
    assert "Rua das Flores" not in enviado
    assert "45 anos" in enviado, "O contexto clínico precisa sobreviver à sanitização"


async def test_stream_sanitiza_antes_de_enviar():
    """O caminho de streaming é código separado — e igualmente obrigatório."""
    espiao = ProviderEspiao()

    async for _ in DlpEnforcingProvider(espiao).stream("modelo-x", PROMPT_COM_PII):
        pass

    enviado = espiao.prompt_recebido
    assert "123.456.789-00" not in enviado
    assert "João Silva" not in enviado


@pytest.mark.parametrize("provider_type", sorted(PROVIDER_TYPE_REGISTRY))
async def test_nenhum_provider_do_registry_recebe_pii(provider_type, monkeypatch):
    """
    Ponta a ponta pelo registry: troca o provider real por um espião e confere
    que o que passa pelo caminho de produção já vem limpo.
    """
    espiao = ProviderEspiao()
    monkeypatch.setitem(PROVIDER_TYPE_REGISTRY, provider_type, espiao)

    await get_provider_by_type(provider_type).complete("modelo-x", PROMPT_COM_PII)

    assert "123.456.789-00" not in espiao.prompt_recebido
    assert "João Silva" not in espiao.prompt_recebido


async def test_sanitizacao_e_idempotente():
    """Sanitizar texto já sanitizado não pode degradar a mensagem."""
    espiao = ProviderEspiao()
    provider = DlpEnforcingProvider(espiao)

    await provider.complete("modelo-x", PROMPT_COM_PII)
    uma_vez = espiao.prompt_recebido
    await provider.complete("modelo-x", uma_vez)

    assert espiao.prompt_recebido == uma_vez


# ── O furo que os testes acima não pegavam ───────────────────────────────────
# Os testes deste arquivo varrem o `PROVIDER_TYPE_REGISTRY` e garantem que todo
# provider DE LÁ sai embrulhado pelo DLP. Mas `orquestrador_shared` instanciava
# `OpenAIProvider()` DIRETAMENTE para o verificador de clarificação — uma
# instância que nunca passava pelo registry, e portanto nunca pelo wrapper.
#
# O verificador recebe o histórico da conversa E o bloco de evolução da pasta.
# Ou seja: o texto mais sensível do produto saía para a OpenAI em claro,
# enquanto a suíte de DLP passava inteira.


def test_nenhum_provider_e_instanciado_fora_do_registry():
    """Instanciar um provider direto contorna o `DlpEnforcingProvider`.

    A única construção legítima é dentro do próprio `ai_providers`, que é onde
    o registry é montado. Qualquer outro módulo do `app/` que faça
    `XProvider()` está abrindo um caminho de saída sem sanitização.
    """
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1] / "app"
    padrao = re.compile(r"\b(\w+Provider)\s*\(\s*\)")

    infratores: list[str] = []
    for arquivo in raiz.rglob("*.py"):
        # `ai_providers` é onde o registry vive: as instâncias de lá são as
        # que o `get_provider_by_type` embrulha.
        if arquivo.name == "ai_providers.py":
            continue
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if linha.lstrip().startswith("#"):
                continue
            for m in padrao.finditer(linha):
                nome = m.group(1)
                if nome == "DlpEnforcingProvider":
                    continue  # é o wrapper, não um provider de saída
                infratores.append(f"{arquivo.relative_to(raiz)}:{n} — {nome}()")

    assert not infratores, (
        "provider instanciado fora do registry (escapa do DLP): "
        + "; ".join(infratores)
        + ". Use get_provider_by_type()."
    )


@pytest.mark.asyncio
async def test_verificador_de_clarificacao_passa_pelo_dlp():
    """O caminho concreto que estava aberto."""
    from app.services import orquestrador_shared

    assert isinstance(
        orquestrador_shared._clarification_provider, DlpEnforcingProvider
    ), "o verificador de clarificação voltou a falar direto com o provedor"


@pytest.mark.asyncio
async def test_evolucao_da_pasta_e_sanitizada_antes_de_gravar():
    """`clinical_context` era o único texto clínico que entrava no banco cru.

    Sanitizar na ESCRITA, e não na leitura, faz o dado identificável deixar de
    existir no banco — em vez de ficar lá esperando o próximo caminho de
    leitura que esqueça de filtrar.
    """
    from app.api.v1.endpoints.folders import _limpar_evolucao

    limpo = await _limpar_evolucao(
        "Jorge Almeida, CPF 123.456.789-00, 58 anos, HAS em acompanhamento"
    )

    assert "123.456.789-00" not in limpo
    assert "Jorge Almeida" not in limpo
    # O conteúdo clínico precisa sobreviver: sanitizar não é apagar.
    assert "58 anos" in limpo
    assert "HAS" in limpo


# ── O wrapper não pode decidir timeout ───────────────────────────────────────
# O `DlpEnforcingProvider` declarava `timeout: int = 30` e repassava esse valor
# SEMPRE. Como todo provider é embrulhado por ele, 30s virava o timeout efetivo
# de todos — anulando os que cada provider define para si.
#
# Em produção isso derrubou o Data Ocean: o `MaritacaProvider` pede 120s porque
# o fluxo agêntico demora, recebia 30, e estourava. O erro era um
# `httpx.ReadTimeout`, cujo `str()` é VAZIO — o log saiu como
# "Stream falhou em sabia-4-thinking: ." e ninguém tinha como saber a causa.


class _ProviderQueRegistraTimeout:
    """Captura o timeout que de fato chegou ao provider."""

    TIMEOUT_PROPRIO = 120

    def __init__(self):
        self.recebido = "NUNCA CHAMADO"

    async def complete(self, model_id, prompt, timeout: int = TIMEOUT_PROPRIO, **kwargs):
        self.recebido = timeout

        class _R:
            text = "ok"
            tokens_in = 1
            tokens_out = 1
            tool_usage = None
            citations = None
        return _R()

    async def stream(self, model_id, prompt, timeout: int = TIMEOUT_PROPRIO, **kwargs):
        self.recebido = timeout
        yield StreamToken(delta="", done=True)


@pytest.mark.asyncio
async def test_o_wrapper_nao_sobrescreve_o_timeout_do_provider():
    """Sem timeout explícito, vale o default de quem conhece a API."""
    interno = _ProviderQueRegistraTimeout()

    await DlpEnforcingProvider(interno).complete("modelo", "prompt")

    assert interno.recebido == _ProviderQueRegistraTimeout.TIMEOUT_PROPRIO, (
        f"o wrapper impôs {interno.recebido}s no lugar do timeout do provider — "
        "foi assim que o Data Ocean estourou em produção"
    )


@pytest.mark.asyncio
async def test_o_wrapper_nao_sobrescreve_o_timeout_no_streaming():
    interno = _ProviderQueRegistraTimeout()

    async for _ in DlpEnforcingProvider(interno).stream("modelo", "prompt"):
        pass

    assert interno.recebido == _ProviderQueRegistraTimeout.TIMEOUT_PROPRIO


@pytest.mark.asyncio
async def test_timeout_explicito_continua_valendo():
    """A contrapartida: quem PEDE um timeout tem o pedido respeitado."""
    interno = _ProviderQueRegistraTimeout()

    await DlpEnforcingProvider(interno).complete("modelo", "prompt", timeout=7)

    assert interno.recebido == 7


def test_o_timeout_do_maritaca_cabe_no_fluxo_agentico():
    """O Data Ocean roda várias consultas antes de devolver a primeira palavra.

    Se alguém baixar este valor para perto dos 30s dos outros providers, o modo
    volta a estourar — e o sintoma é um erro sem mensagem.
    """
    from app.services.integracoes.ai_providers import MaritacaProvider

    assert MaritacaProvider.TIMEOUT_FERRAMENTAS >= 90
