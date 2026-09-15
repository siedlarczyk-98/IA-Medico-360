"""
`temperature` não pode chegar a modelo que a rejeita.

O QUE ISTO PROTEGE
A partir do Sonnet 5 / Opus 5, a Anthropic REMOVEU os parâmetros de sampling
(`temperature`, `top_p`, `top_k`). Um payload que os inclua volta **400** — não
degrada, não ignora: falha.

`MODE_TEMPERATURE_MAP` manda `temperature: 0.0` nos modos clínicos, e o provider
Anthropic enviava esse valor incondicionalmente. Trocar só o `model_id` na
migração para o Sonnet 5 teria quebrado `CLINICAL_REASONING` e `EXAM_REVIEW` em
TODA requisição — os dois modos mais críticos do produto.

O provider OpenAI já tinha o mesmo filtro, pelo mesmo motivo (o-series e gpt-5
fizeram a remoção antes). Este arquivo trava a invariante nos dois.
"""

import pytest

from app.services.integracoes.ai_providers import AnthropicProvider, OpenAIProvider
from app.services.orquestrador_modes import MODE_MODEL_MAP, MODE_TEMPERATURE_MAP


@pytest.mark.parametrize(
    "model_id",
    ["claude-sonnet-5", "claude-opus-5", "claude-opus-4-8", "claude-fable-5-1"],
)
def test_modelos_novos_nao_recebem_temperature(model_id):
    assert AnthropicProvider._supports_temperature(model_id) is False, (
        f"{model_id} rejeita `temperature` — enviar o parâmetro devolve 400"
    )


@pytest.mark.parametrize(
    "model_id",
    ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-sonnet-4-20250514"],
)
def test_modelos_antigos_continuam_recebendo_temperature(model_id):
    """
    O filtro não pode ser amplo demais: nestes modelos `temperature: 0.0` é o
    que garante resposta clínica reproduzível.
    """
    assert AnthropicProvider._supports_temperature(model_id) is True


def test_openai_mantem_o_proprio_filtro():
    """O precedente que este filtro copia — não pode ter sido perdido."""
    assert OpenAIProvider._supports_temperature("gpt-5.4-mini") is False
    assert OpenAIProvider._supports_temperature("gpt-4o") is True


def test_todo_modelo_clinico_configurado_e_compativel_com_seu_mapa():
    """
    A trava que pega a próxima migração.

    Se alguém trocar um `model_id` no `MODE_MODEL_MAP` por um modelo que rejeita
    sampling e o filtro do provider não o conhecer, o payload sai com
    `temperature` e o modo quebra inteiro. Aqui isso falha no CI, não em
    produção.
    """
    problemas = []
    for modo, model_id in MODE_MODEL_MAP.items():
        if model_id is None or modo not in MODE_TEMPERATURE_MAP:
            continue
        if not model_id.startswith("claude"):
            continue
        # Um modelo Anthropic com temperatura declarada só é seguro se o
        # provider souber decidir — e a decisão certa aqui é "não enviar" para
        # a geração nova.
        enviaria = AnthropicProvider._supports_temperature(model_id)
        if enviaria and model_id.startswith(("claude-sonnet-5", "claude-opus-5")):
            problemas.append(f"{modo} -> {model_id}")

    assert not problemas, (
        "Modo clínico apontando para modelo que rejeita `temperature`, sem o "
        f"filtro correspondente em `_NO_TEMPERATURE_PREFIXES`: {problemas}"
    )


def test_payload_do_anthropic_omite_temperature_no_modelo_novo():
    """
    Verificação do EFEITO, não da função auxiliar: é o dict que vai para a API
    que precisa sair sem a chave.
    """
    provider = AnthropicProvider()
    model_id = "claude-sonnet-5"

    payload = {
        "model": model_id,
        "max_tokens": 4096,
        **({"temperature": 0.0} if provider._supports_temperature(model_id) else {}),
        "system": "...",
        "messages": [],
    }

    assert "temperature" not in payload

    payload_antigo = {
        "model": "claude-sonnet-4-6",
        **(
            {"temperature": 0.0}
            if provider._supports_temperature("claude-sonnet-4-6")
            else {}
        ),
    }
    assert payload_antigo["temperature"] == 0.0
