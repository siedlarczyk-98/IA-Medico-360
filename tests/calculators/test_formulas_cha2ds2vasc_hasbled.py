"""
Golden values do CHA2DS2-VASc + HAS-BLED.

CHA2DS2-VASc: ICC(1), HAS(1), Idade>=75(2) / 65-74(1), DM(1), AVC/AIT ou TEV prévio(2),
              doença vascular(1), sexo feminino(1). Máximo 9.
HAS-BLED: HAS não controlada(1), função renal alterada(1), função hepática alterada(1),
          AVC/AIT prévio(1) — TEV isolado NÃO conta aqui (critério "S" é AVC), sangramento
          prévio(1), INR lábil(1), idade>65(1), álcool/drogas(1), medicamentos
          predisponentes(1). Máximo 9.

Valores esperados derivados da definição dos escores (ESC AF guidelines;
Pisters et al., Chest 2010;138:1093-100), não da leitura do código.
"""

import pytest

from app.calculators.formulas.cardiologia.cha2ds2vasc_hasbled import calculate


def _scores(out: dict) -> dict[str, int]:
    return {s["key"]: s["value"] for s in out["result"]["scores"]}


def test_todos_negativos_masculino():
    out = calculate({"idade": 50, "sexo": "M"})
    s = _scores(out)
    assert s["chads_vasc"] == 0
    assert s["has_bled"] == 0


def test_todos_positivos_masculino_80a():
    inputs = dict(
        idade=80, sexo="M",
        icc=True, hipertensao=True, diabetes=True,
        avc_ait_previo=True, doenca_vascular=True,
        hipertensao_nao_controlada=True, funcao_renal_alterada=True,
        funcao_hepatica_alterada=True, sangramento_previo=True, inr_labil=True,
        uso_alcool_drogas=True, medicamentos_predisponentes_sangramento=True,
    )
    s = _scores(calculate(inputs))
    # CHADS: icc1+has1+idade>=75(2)+dm1+avc2+vascular1 = 8 (masculino não soma sexo)
    assert s["chads_vasc"] == 8
    # HAS-BLED: 9 fatores presentes
    assert s["has_bled"] == 9


def test_feminino_70a_isolado():
    out = calculate({"idade": 70, "sexo": "F"})
    s = _scores(out)
    # CHADS: idade 65-74 (1) + sexo feminino (1) = 2
    assert s["chads_vasc"] == 2
    # HAS-BLED: idade > 65 (1)
    assert s["has_bled"] == 1


@pytest.mark.parametrize(
    "idade, chads_idade, hasbled_idade",
    [
        (64, 0, 0),   # < 65 em ambos
        (65, 1, 0),   # CHADS 65-74=1; HAS-BLED é > 65 (65 não conta)
        (66, 1, 1),
        (75, 2, 1),   # CHADS idade>=75=2
    ],
)
def test_bordas_idade(idade, chads_idade, hasbled_idade):
    s = _scores(calculate({"idade": idade, "sexo": "M"}))
    assert s["chads_vasc"] == chads_idade
    assert s["has_bled"] == hasbled_idade


def test_avc_previo_soma_nos_dois_escores():
    s = _scores(calculate({"idade": 50, "sexo": "M", "avc_ait_previo": True}))
    assert s["chads_vasc"] == 2   # AVC/AIT prévio vale 2 no CHADS
    assert s["has_bled"] == 1     # e 1 no HAS-BLED (critério "S")


def test_tev_isolado_soma_so_no_chads():
    s = _scores(calculate({"idade": 50, "sexo": "M", "tev_previo": True}))
    assert s["chads_vasc"] == 2   # TEV prévio também vale 2 no CHADS
    assert s["has_bled"] == 0     # mas NÃO conta no HAS-BLED (critério "S" é só AVC)


def test_ambos_escores_sempre_presentes():
    out = calculate({"idade": 50, "sexo": "M"})
    keys = {s["key"] for s in out["result"]["scores"]}
    assert keys == {"chads_vasc", "has_bled"}
