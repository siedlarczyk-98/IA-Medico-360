"""
Tradução do histórico para o formato nativo de cada provider.

Os quatro provedores mandavam UMA única mensagem `user` com a conversa inteira
achatada dentro. Agora recebem turnos, e cada um os representa de um jeito:
Anthropic e OpenAI usam `messages` com `assistant`, Gemini usa `contents` com
`model` e o texto dentro de `parts`, e Perplexity exige alternância estrita
começando por `user` depois do `system`.

Um erro de tradução aqui não quebra nada visivelmente — o modelo só passa a
receber contexto malformado e responde pior. Daí os testes.
"""

import pytest

from app.services.ai_providers import (
    AnthropicProvider,
    DlpEnforcingProvider,
    GeminiProvider,
    OpenAIProvider,
    PerplexityProvider,
)

HISTORICO = [
    {"role": "user", "content": "paciente com cefaleia ha 1 mes"},
    {"role": "assistant", "content": "considerar enxaqueca; investigar sinais de alarme"},
]


class ClienteFalso:
    """Captura o payload enviado, sem sair para a rede."""

    def __init__(self, resposta: dict):
        self.resposta = resposta
        self.payload = None

    async def post(self, url, **kwargs):
        self.payload = kwargs.get("json")

        class Resp:
            status_code = 200

            def raise_for_status(_self):
                return None

            def json(_self):
                return self.resposta

        return Resp()


def _instalar_cliente(monkeypatch, modulo_resposta):
    cliente = ClienteFalso(modulo_resposta)
    monkeypatch.setattr("app.services.ai_providers.get_client", lambda: cliente)
    return cliente


# ── Anthropic ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anthropic_manda_turnos_antes_da_pergunta_atual(monkeypatch):
    cliente = _instalar_cliente(monkeypatch, {
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })

    await AnthropicProvider().complete(
        "claude-sonnet-4-6", "e agora?", system_prompt="sys", history=HISTORICO
    )

    mensagens = cliente.payload["messages"]
    assert [m["role"] for m in mensagens] == ["user", "assistant", "user"]
    assert mensagens[0]["content"] == "paciente com cefaleia ha 1 mes"
    # A pergunta atual precisa ser a última — é a que o modelo deve responder.
    assert mensagens[-1]["content"] == "e agora?"


# ── OpenAI ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_openai_mantem_system_primeiro_e_historico_depois(monkeypatch):
    cliente = _instalar_cliente(monkeypatch, {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    })

    await OpenAIProvider().complete(
        "gpt-5.4-nano", "e agora?", system_prompt="sys", history=HISTORICO
    )

    papeis = [m["role"] for m in cliente.payload["messages"]]
    assert papeis == ["system", "user", "assistant", "user"]


# ── Gemini ───────────────────────────────────────────────────────────────────

def test_gemini_traduz_assistant_para_model():
    """No Gemini o papel do assistente chama-se `model`; mandar `assistant` é erro."""
    contents = GeminiProvider._history_to_contents(HISTORICO)

    assert [c["role"] for c in contents] == ["user", "model"]
    assert contents[0]["parts"] == [{"text": "paciente com cefaleia ha 1 mes"}]


def test_gemini_sem_historico_devolve_lista_vazia():
    assert GeminiProvider._history_to_contents(None) == []
    assert GeminiProvider._history_to_contents([]) == []


@pytest.mark.asyncio
async def test_gemini_poe_a_pergunta_atual_por_ultimo(monkeypatch):
    cliente = _instalar_cliente(monkeypatch, {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
        "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
    })

    await GeminiProvider().complete(
        "gemini-2.5-flash", "e agora?", system_prompt="sys", history=HISTORICO
    )

    contents = cliente.payload["contents"]
    assert [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[-1]["parts"][-1]["text"] == "e agora?"


# ── Perplexity ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_perplexity_alterna_estritamente_apos_o_system(monkeypatch):
    """A API rejeita a requisição se os papéis não alternarem."""
    cliente = _instalar_cliente(monkeypatch, {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    })

    await PerplexityProvider().complete(
        "sonar-pro", "e agora?", system_prompt="sys", history=HISTORICO
    )

    papeis = [m["role"] for m in cliente.payload["messages"]]
    assert papeis == ["system", "user", "assistant", "user"]

    depois_do_system = papeis[1:]
    for anterior, seguinte in zip(depois_do_system, depois_do_system[1:], strict=False):
        assert anterior != seguinte, f"papéis repetidos em sequência: {papeis}"


# ── Rede de segurança do DLP ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dlp_sanitiza_o_historico_tambem(monkeypatch):
    """
    Sem isto a rede de segurança teria um buraco do tamanho da conversa: o
    prompt atual sairia limpo, mas o mesmo dado de paciente escrito três
    mensagens atrás viajaria intacto a cada nova pergunta.
    """
    capturado = {}

    class ProviderEspiao:
        async def complete(self, model_id, prompt, **kwargs):
            capturado["history"] = kwargs.get("history")
            capturado["prompt"] = prompt

            class R:
                text = "ok"
                tokens_in = tokens_out = 1
                citations = None
            return R()

        async def stream(self, *a, **k):
            yield None

    historico_com_pii = [
        {"role": "user", "content": "paciente Joao Silva, CPF 529.982.247-25"},
    ]

    await DlpEnforcingProvider(ProviderEspiao()).complete(
        "m", "pergunta limpa", history=historico_com_pii
    )

    conteudo = capturado["history"][0]["content"]
    assert "529.982.247-25" not in conteudo, "CPF vazou pelo histórico"
    assert "[DOCUMENTO]" in conteudo


@pytest.mark.asyncio
async def test_dlp_preserva_o_papel_ao_sanitizar(monkeypatch):
    capturado = {}

    class ProviderEspiao:
        async def complete(self, model_id, prompt, **kwargs):
            capturado["history"] = kwargs.get("history")

            class R:
                text = "ok"
                tokens_in = tokens_out = 1
                citations = None
            return R()

        async def stream(self, *a, **k):
            yield None

    await DlpEnforcingProvider(ProviderEspiao()).complete("m", "p", history=HISTORICO)

    assert [m["role"] for m in capturado["history"]] == ["user", "assistant"]
