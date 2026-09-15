"""
Prompt caching — o breakpoint fica no fim do histórico.

O QUE ISTO PROTEGE
Caching é prefix match: o que estiver antes do breakpoint é reaproveitado entre
requisições, e qualquer byte que mude invalida tudo depois dele. As três formas
de errar aqui não quebram nada visivelmente — só fazem a conta subir, em
silêncio, por meses:

1. **Breakpoint no system.** O system clínico tem ~460 tokens (com o sufixo do
   médico) e o mínimo cacheável no Sonnet é 1024. A API não erra: devolve
   `cache_creation_input_tokens: 0` e segue. Nunca cacheia nada.
2. **Breakpoint automático.** Ele se coloca no último bloco cacheável — que aqui
   é a PERGUNTA ATUAL, única por requisição. Paga o prêmio de escrita (1,25x)
   em bytes que ninguém relê, toda vez. Sobretaxa pura.
3. **Marcação perdida numa refatoração.** Alguém volta a montar `messages` com
   `*(history or [])` e o caching desaparece sem nenhum teste reclamar.

A verificação real em produção é `usage.cache_read_input_tokens`: zero em
requisições consecutivas do mesmo médico na mesma conversa significa que há um
invalidador no prefixo.
"""

import pytest

from app.services.integracoes.ai_providers import AnthropicProvider

HISTORICO = [
    {"role": "user", "content": "paciente 62 anos, FA nao valvar, clearance 28"},
    {"role": "assistant", "content": "anticoagulacao indicada; ajustar pelo clearance"},
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


def _instalar_cliente(monkeypatch):
    cliente = ClienteFalso({
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })
    monkeypatch.setattr("app.services.integracoes.ai_providers.get_client", lambda: cliente)
    return cliente


def _breakpoints(mensagens: list[dict]) -> list[int]:
    """Índices das mensagens que carregam `cache_control`."""
    indices = []
    for i, m in enumerate(mensagens):
        conteudo = m.get("content")
        if isinstance(conteudo, list) and any(
            isinstance(b, dict) and "cache_control" in b for b in conteudo
        ):
            indices.append(i)
    return indices


# ── A marcação existe e está no lugar certo ──────────────────────────────


@pytest.mark.asyncio
async def test_breakpoint_fica_no_ultimo_turno_do_historico(monkeypatch):
    cliente = _instalar_cliente(monkeypatch)

    await AnthropicProvider().complete(
        "claude-sonnet-5", "e qual a dose?", system_prompt="sys", history=HISTORICO
    )

    mensagens = cliente.payload["messages"]
    # history (2) + pergunta atual (1)
    assert len(mensagens) == 3
    assert _breakpoints(mensagens) == [1], (
        "O breakpoint precisa estar no ÚLTIMO turno do histórico — índice 1 aqui"
    )


@pytest.mark.asyncio
async def test_pergunta_atual_fica_fora_do_cache(monkeypatch):
    """
    O conteúdo único de cada requisição tem de ficar DEPOIS do corte. Marcá-lo
    faria cada pergunta escrever uma entrada que nunca é lida de volta.
    """
    cliente = _instalar_cliente(monkeypatch)

    await AnthropicProvider().complete(
        "claude-sonnet-5", "e qual a dose?", system_prompt="sys", history=HISTORICO
    )

    ultima = cliente.payload["messages"][-1]
    assert ultima["content"] == "e qual a dose?"
    assert not isinstance(ultima["content"], list), (
        "A pergunta atual não pode carregar `cache_control`"
    )


@pytest.mark.asyncio
async def test_stream_marca_igual_ao_complete(monkeypatch):
    """
    Os dois caminhos precisam ter o MESMO prefixo, senão cada um escreve a
    própria entrada e nenhum lê a do outro. É a divergência `/query`↔`/stream`
    que este projeto já teve quatro vezes, agora em forma de custo.
    """
    capturado = {}

    class ClienteStream:
        def stream(self, method, url, **kwargs):
            capturado["payload"] = kwargs.get("json")

            class Ctx:
                async def __aenter__(_self):
                    class Resp:
                        status_code = 200

                        def raise_for_status(_s):
                            return None

                        async def aiter_lines(_s):
                            return
                            yield  # pragma: no cover

                    return Resp()

                async def __aexit__(_self, *a):
                    return False

            return Ctx()

    monkeypatch.setattr(
        "app.services.integracoes.ai_providers.get_client", lambda: ClienteStream()
    )

    agen = AnthropicProvider().stream(
        "claude-sonnet-5", "e qual a dose?", system_prompt="sys", history=HISTORICO
    )
    _ = [t async for t in agen]

    mensagens = capturado["payload"]["messages"]
    assert _breakpoints(mensagens) == [1]


# ── Casos de borda ───────────────────────────────────────────────────────


def test_sem_historico_nao_marca_nada():
    """
    Primeira pergunta da conversa: não há prefixo estável a reaproveitar, e
    marcar aqui pagaria escrita sem nunca haver leitura.
    """
    assert AnthropicProvider._com_breakpoint_de_cache(None) == []
    assert AnthropicProvider._com_breakpoint_de_cache([]) == []


def test_marcacao_nao_altera_o_historico_original():
    """
    O provider recebe a mesma lista que o resto do pipeline usa. Mutá-la faria o
    `cache_control` vazar para lugares que não o esperam — incluindo o que é
    gravado e o que vai para outros providers no agregador.
    """
    original = [dict(m) for m in HISTORICO]
    AnthropicProvider._com_breakpoint_de_cache(HISTORICO)

    assert HISTORICO == original, "o histórico de entrada foi modificado in-place"


def test_conteudo_em_blocos_recebe_a_marcacao_no_ultimo_bloco():
    """Mensagem com imagem+texto chega como lista de blocos."""
    historico = [
        {"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}},
            {"type": "text", "text": "o que voce ve?"},
        ]},
    ]

    marcado = AnthropicProvider._com_breakpoint_de_cache(historico)

    blocos = marcado[-1]["content"]
    assert "cache_control" not in blocos[0]
    assert blocos[-1]["cache_control"] == {"type": "ephemeral"}


def test_formato_inesperado_nao_estoura():
    """
    Conteúdo vazio ou de tipo estranho não pode derrubar a requisição: perder o
    cache é aceitável, perder a resposta do médico não.
    """
    historico = [{"role": "user", "content": None}]

    marcado = AnthropicProvider._com_breakpoint_de_cache(historico)

    assert len(marcado) == 1
    assert _breakpoints(marcado) == []
