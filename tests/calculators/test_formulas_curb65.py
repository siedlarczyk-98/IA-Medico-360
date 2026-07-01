"""
Golden values do CURB-65 (Lim WS et al., Thorax 2003;58:377-82).

1 ponto para cada critério presente:
  - Confusão mental
  - Ureia > 42,8 mg/dL (~7 mmol/L)
  - Frequência respiratória >= 30 irpm
  - PAS < 90 mmHg OU PAD <= 60 mmHg
  - Idade >= 65 anos
Estratificação: 0-1 baixo, 2 intermediário, >=3 alto.

Os valores esperados abaixo são derivados da definição do escore, não da
leitura do código, para não validar um eventual bug de implementação.
"""

import pytest

from app.calculators.formulas.infectologia.curb65 import calculate


def _score(out: dict) -> int:
    return out["result"]["primary"]["value"]


BASE_NEGATIVO = dict(
    confusao_mental=False,
    ureia_mgdl=30,
    fr_irpm=18,
    pas_mmhg=120,
    pad_mmhg=80,
    idade=50,
)


@pytest.mark.parametrize(
    "override, esperado",
    [
        ({}, 0),                                                    # nenhum critério
        ({"confusao_mental": True}, 1),
        ({"ureia_mgdl": 50}, 1),                                    # ureia > 42,8
        ({"fr_irpm": 30}, 1),                                       # limiar >= 30
        ({"pas_mmhg": 85}, 1),                                      # PAS < 90
        ({"pad_mmhg": 60}, 1),                                      # PAD <= 60 (limiar)
        ({"idade": 65}, 1),                                         # idade >= 65 (limiar)
        ({"idade": 65, "ureia_mgdl": 50}, 2),                       # intermediário
        ({"idade": 65, "ureia_mgdl": 50, "confusao_mental": True}, 3),
        (dict(confusao_mental=True, ureia_mgdl=50, fr_irpm=32,
              pas_mmhg=85, pad_mmhg=60, idade=70), 5),              # todos os critérios
    ],
)
def test_curb65_score(override, esperado):
    inputs = {**BASE_NEGATIVO, **override}
    assert _score(calculate(inputs)) == esperado


@pytest.mark.parametrize(
    "override, sem_criterio",
    [
        ({"ureia_mgdl": 42.8}, "ureia no limiar exato não pontua (é > e não >=)"),
        ({"fr_irpm": 29}, "FR 29 não pontua"),
        ({"pas_mmhg": 90}, "PAS 90 não pontua (é < 90)"),
        ({"pad_mmhg": 61}, "PAD 61 não pontua"),
        ({"idade": 64}, "idade 64 não pontua"),
    ],
)
def test_curb65_bordas_negativas(override, sem_criterio):
    inputs = {**BASE_NEGATIVO, **override}
    assert _score(calculate(inputs)) == 0, sem_criterio


@pytest.mark.parametrize(
    "score, trecho",
    [
        (0, "ambulatorial"),
        (2, "internação"),
        (3, "UTI"),
    ],
)
def test_curb65_interpretacao(score, trecho):
    # constrói um input que gera exatamente `score`
    overrides = {
        0: {},
        2: {"idade": 65, "ureia_mgdl": 50},
        3: {"idade": 65, "ureia_mgdl": 50, "confusao_mental": True},
    }[score]
    out = calculate({**BASE_NEGATIVO, **overrides})
    assert trecho.lower() in out["interpretation"].lower()
