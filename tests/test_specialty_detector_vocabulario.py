"""
O classificador de perguntas passou a falar o mesmo vocabulário do resto.

Antes, as 31 opções eram nomes CURTOS escritos à mão no próprio arquivo
("Ortopedia", "Endocrinologia", "Clínica Geral") — incompatíveis com os nomes
completos do CFM que `users.specialty` guarda. Como a saída vai para
`interactions.specialty_detected`, qualquer cruzamento entre "a especialidade da
pergunta" e "a especialidade do médico" comparava grafias diferentes da mesma
coisa. Resultado errado, sem erro nenhum aparecendo.
"""

import json

import pytest

from app.medicina import especialidades
from app.services import cache_service, specialty_detector


def test_prompt_usa_o_vocabulario_canonico():
    for nome in especialidades.nomes_para_detector():
        assert nome in specialty_detector.CLASSIFICATION_PROMPT, nome


def test_prompt_nao_tem_mais_os_nomes_curtos():
    """Os que colidiam: se voltarem, o dado volta a divergir em silêncio."""
    linha_opcoes = next(
        ln for ln in specialty_detector.CLASSIFICATION_PROMPT.splitlines()
        if ln.startswith("Opções válidas:")
    )
    for curto in ("Clínica Geral", "Medicina Esportiva"):
        assert curto not in linha_opcoes


def test_placeholder_sobreviveu_a_f_string():
    """A lista virou interpolada; `{prompt}` precisa continuar sendo placeholder."""
    assert "{prompt}" in specialty_detector.CLASSIFICATION_PROMPT
    montado = specialty_detector.CLASSIFICATION_PROMPT.format(prompt="dose de amox")
    assert "dose de amox" in montado


def _responder(monkeypatch, conteudo: str):
    """Finge a resposta da OpenAI e desliga o cache entre casos."""
    class RespostaFake:
        status_code = 200

        def raise_for_status(self): ...

        def json(self):
            return {"choices": [{"message": {"content": conteudo}}]}

    class ClienteFake:
        async def post(self, *a, **k):
            return RespostaFake()

    monkeypatch.setattr(specialty_detector, "get_client", lambda: ClienteFake())

    async def sem_cache(_key):
        return None

    async def nao_grava(*a, **k): ...

    monkeypatch.setattr(cache_service, "get_json", sem_cache)
    monkeypatch.setattr(cache_service, "set_json", nao_grava)


@pytest.mark.asyncio
async def test_nome_curto_do_modelo_vira_rotulo_canonico(monkeypatch):
    """O modelo às vezes responde fora da lista apesar da instrução.

    Sem normalizar, "Ortopedia" entraria no banco como se fosse vocabulário
    nosso — e nunca casaria com o "Ortopedia e Traumatologia" dos usuários.
    """
    _responder(monkeypatch, json.dumps({"specialty": "Ortopedia", "topic": "fratura"}))

    out = await specialty_detector.detect_specialty_and_topic("dor no punho")

    assert out["specialty"] == "Ortopedia e Traumatologia"


@pytest.mark.asyncio
async def test_especialidade_irreconhecivel_vira_none_e_alerta(monkeypatch, caplog):
    """Melhor gravar nada do que gravar uma string que ninguém consegue cruzar."""
    _responder(monkeypatch, json.dumps({"specialty": "Medicina Quântica", "topic": "x"}))

    with caplog.at_level("WARNING"):
        out = await specialty_detector.detect_specialty_and_topic("pergunta esquisita")

    assert out["specialty"] is None
    assert "Medicina Quântica" in caplog.text


@pytest.mark.asyncio
async def test_nao_clinico_continua_passando(monkeypatch):
    _responder(monkeypatch, json.dumps({"specialty": "NAO_CLINICO", "topic": "gestão"}))

    out = await specialty_detector.detect_specialty_and_topic("como abrir consultório")

    assert out["specialty"] == specialty_detector.NAO_CLINICO
