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
