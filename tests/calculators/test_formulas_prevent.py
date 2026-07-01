"""
Golden values do PREVENT (Khan et al., Circulation 2024, Material Suplementar).

Ancorado no exemplo numérico publicado no paper (p. 441), reproduzido no docstring
de app/calculators/formulas/cardiologia/prevent.py:
  mulher 50a, CT 240 mg/dL, HDL-c 55 mg/dL, sem estatina, PAS tratada 160 mmHg,
  sem DM, eGFR 90, IMC 35
    -> CVD 5,4% / ASCVD 3,6% / HF 2,5%   (sem fumo)
    -> ASCVD 6,0% / HF 4,7%              (com fumo)
"""

import pytest

from app.calculators.formulas.cardiologia.prevent import prevent_risk

EXEMPLO = dict(
    sex="F", age=50, tc_mgdl=240, hdl_mgdl=55, sbp=160,
    diabetes=False, antihtn_use=True, statin_use=False, egfr=90, bmi=35,
    horizon=10,
)


@pytest.mark.parametrize(
    "outcome, smoker, esperado",
    [
        ("ascvd", False, 3.6),
        ("ascvd", True, 6.0),
        ("cvd", False, 5.4),
        ("hf", False, 2.5),
        ("hf", True, 4.7),
    ],
)
def test_exemplo_publicado(outcome, smoker, esperado):
    risco = prevent_risk(**EXEMPLO, outcome=outcome, smoker=smoker)
    assert risco == pytest.approx(esperado, abs=0.1)


def test_hf_exige_bmi():
    args = {**EXEMPLO, "smoker": False}
    args.pop("bmi")
    with pytest.raises(ValueError):
        prevent_risk(**args, outcome="hf", bmi=None)


def test_risco_monotonico_com_fumo():
    sem = prevent_risk(**EXEMPLO, outcome="ascvd", smoker=False)
    com = prevent_risk(**EXEMPLO, outcome="ascvd", smoker=True)
    assert com > sem


def test_resultado_em_faixa_percentual():
    risco = prevent_risk(**EXEMPLO, outcome="ascvd", smoker=False)
    assert 0 < risco < 100
