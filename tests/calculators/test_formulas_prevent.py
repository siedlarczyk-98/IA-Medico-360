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

from app.calculators.formulas.cardiologia.prevent import prevent_all, prevent_avisos, prevent_risk

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


# ── Faixas de validade, espelhando AHAprevent::pred_risk_base ────────────────

BASE_VALIDA = dict(
    sex="F", age=50, tc_mgdl=240, hdl_mgdl=55, sbp=160, diabetes=False,
    smoker=False, antihtn_use=True, statin_use=False, egfr=90, bmi=35,
)

# Listados à mão de propósito: se fossem derivados do módulo, o teste passaria a
# comparar a implementação consigo mesma e não afirmaria nada.
TODOS = {
    "cvd_10a", "ascvd_10a", "chd_10a", "stroke_10a", "hf_10a",
    "cvd_30a", "ascvd_30a", "chd_30a", "stroke_30a", "hf_30a",
}
LIPIDICOS = {
    "cvd_10a", "ascvd_10a", "chd_10a", "stroke_10a",
    "cvd_30a", "ascvd_30a", "chd_30a", "stroke_30a",
}
HF = {"hf_10a", "hf_30a"}
TRINTA_ANOS = {"cvd_30a", "ascvd_30a", "chd_30a", "stroke_30a", "hf_30a"}


def _nulos(**alteracoes) -> set[str]:
    r = prevent_all(**{**BASE_VALIDA, **alteracoes})
    return {campo for campo, valor in r.items() if valor is None}


def test_paciente_valido_devolve_os_seis_desfechos():
    assert _nulos() == set()


@pytest.mark.parametrize(
    "descricao, alteracao, esperado_nulo",
    [
        # A regra que mais importa: IMC só entra nas equações de HF, então IMC
        # fora de faixa não pode derrubar ASCVD/CVD (era o comportamento antigo,
        # que rebaixava obeso grave para a trilha de baixo risco).
        ("IMC 42 (obesidade grave)", dict(bmi=42), HF),
        ("IMC 40 exato", dict(bmi=40), HF),
        ("IMC 17 (baixo peso)", dict(bmi=17), HF),
        ("IMC 39,9 ainda vale", dict(bmi=39.9), set()),
        ("IMC 18,5 ainda vale", dict(bmi=18.5), set()),
        ("CT 400 acima da faixa", dict(tc_mgdl=400), LIPIDICOS),
        ("CT 120 abaixo da faixa", dict(tc_mgdl=120), LIPIDICOS),
        ("HDL 15 abaixo da faixa", dict(hdl_mgdl=15), LIPIDICOS),
        ("HDL 110 acima da faixa", dict(hdl_mgdl=110), LIPIDICOS),
        ("PAS 210 derruba tudo", dict(sbp=210), TODOS),
        ("PAS 80 derruba tudo", dict(sbp=80), TODOS),
        ("TFGe zero derruba tudo", dict(egfr=0), TODOS),
        ("idade 65 derruba só os 30 anos", dict(age=65), TRINTA_ANOS),
        ("idade 59 ainda tem 30 anos", dict(age=59), set()),
        ("idade 85 derruba tudo", dict(age=85), TODOS),
        ("idade 25 derruba tudo", dict(age=25), TODOS),
    ],
)
def test_faixas_invalidam_por_desfecho(descricao, alteracao, esperado_nulo):
    assert _nulos(**alteracao) == esperado_nulo, descricao


def test_imc_invalido_nao_altera_o_ascvd():
    """IMC não entra na equação de ASCVD — o valor tem de ser idêntico."""
    com_imc_valido = prevent_all(**BASE_VALIDA)
    com_imc_alto = prevent_all(**{**BASE_VALIDA, "bmi": 42})
    assert com_imc_alto["ascvd_10a"] == com_imc_valido["ascvd_10a"]


# ── Avisos: toda célula vazia precisa de justificativa ───────────────────────


def _codigos(**alteracoes) -> list[str]:
    return [a["codigo"] for a in prevent_avisos(**{**BASE_VALIDA, **alteracoes})]


def test_paciente_valido_nao_gera_aviso():
    assert _codigos() == []


@pytest.mark.parametrize(
    "alteracao, codigo",
    [
        (dict(age=85), "idade_fora_30_79"),
        (dict(age=25), "idade_fora_30_79"),
        (dict(age=65), "idade_acima_59"),
        (dict(tc_mgdl=400), "ct_fora_130_320"),
        (dict(hdl_mgdl=110), "hdl_fora_20_100"),
        (dict(sbp=210), "pas_fora_90_200"),
        (dict(egfr=0), "egfr_nao_positiva"),
        (dict(bmi=42), "imc_fora_18_5_39_9"),
    ],
)
def test_cada_faixa_tem_seu_aviso(alteracao, codigo):
    assert codigo in _codigos(**alteracao)


def test_idade_fora_da_faixa_nao_repete_o_aviso_dos_30_anos():
    """Aos 85 anos nada é calculado; falar de projeção de 30 anos só confunde."""
    assert _codigos(age=85) == ["idade_fora_30_79"]


def test_todo_desfecho_vazio_tem_aviso_que_o_explique():
    """
    A trava que importa: nenhuma célula pode ficar vazia sem justificativa na
    tela, senão é indistinguível de bug. Vale para cada combinação abaixo.
    """
    cenarios = [
        dict(), dict(age=85), dict(age=65), dict(bmi=42), dict(bmi=17),
        dict(tc_mgdl=400), dict(hdl_mgdl=110), dict(sbp=210), dict(egfr=0),
        dict(age=65, bmi=42), dict(age=70, tc_mgdl=400),
    ]
    for alteracao in cenarios:
        args = {**BASE_VALIDA, **alteracao}
        vazios = {campo for campo, valor in prevent_all(**args).items() if valor is None}
        explicados = {c for a in prevent_avisos(**args) for c in a["desfechos"]}
        assert vazios <= explicados, f"sem justificativa em {alteracao}: {vazios - explicados}"


def test_aviso_nao_promete_o_que_a_conta_entregou():
    """O inverso: não avisar sobre desfecho que foi calculado normalmente."""
    for alteracao in [dict(age=65), dict(bmi=42), dict(tc_mgdl=400)]:
        args = {**BASE_VALIDA, **alteracao}
        calculados = {campo for campo, valor in prevent_all(**args).items() if valor is not None}
        citados = {c for a in prevent_avisos(**args) for c in a["desfechos"]}
        assert not (calculados & citados), f"aviso sobra em {alteracao}: {calculados & citados}"


# ── Golden values ────────────────────────────────────────────────────────────
#
# Seis perfis que exercitam braços distintos do modelo. Dois têm âncora externa:
#   A — exemplo numérico publicado em Khan et al. 2024 (p. 441).
#   E — conferido contra a tela do MDCalc em 2026-08-28 nos oito valores que ele
#       exibe: DCV 12,87/42,45, ASCVD 8,45/28,95, coronariana 4,97/18,84 e
#       AVC 3,70/14,12 (10 e 30 anos). O MDCalc não exibe IC.
# Os outros quatro são travas de regressão, geradas por esta implementação
# depois de ela ter sido conferida coeficiente a coeficiente contra a codebase
# da AHA (`AHAprevent::pred_risk_base`). Não são verdade externa — servem para
# detectar mudança acidental de comportamento, que é o que se quer aqui.
#
# Cada caso cobre algo que os demais não cobrem: B é o meio da faixa sem nenhum
# fator, C força o corte dos 30 anos por idade, D exercita o braço de TFGe < 60
# (coeficiente e interação com idade próprios), E o corte de IMC, F a ponta de
# risco muito baixo.

GOLDEN = {
    "A exemplo publicado (F 50a, PAS tratada)": (
        dict(sex="F", age=50, tc_mgdl=240, hdl_mgdl=55, sbp=160, diabetes=False,
             smoker=False, antihtn_use=True, statin_use=False, egfr=90, bmi=35),
        dict(cvd_10a=5.4274, ascvd_10a=3.6376, chd_10a=1.5723, stroke_10a=2.1260, hf_10a=2.5280,
             cvd_30a=30.6699, ascvd_30a=19.8564, chd_30a=9.5900, stroke_30a=11.7224, hf_30a=18.4750),
    ),
    "B homem médio, sem fatores": (
        dict(sex="M", age=45, tc_mgdl=200, hdl_mgdl=45, sbp=125, diabetes=False,
             smoker=False, antihtn_use=False, statin_use=False, egfr=95, bmi=27),
        dict(cvd_10a=2.1881, ascvd_10a=1.5376, chd_10a=0.8637, stroke_10a=0.6423, hf_10a=0.6729,
             cvd_30a=15.3580, ascvd_30a=10.2205, chd_30a=6.1518, stroke_30a=4.4876, hf_30a=6.1456),
    ),
    "C idoso com DM e tabagismo (corta os 30 anos)": (
        dict(sex="M", age=68, tc_mgdl=210, hdl_mgdl=38, sbp=150, diabetes=True,
             smoker=True, antihtn_use=True, statin_use=True, egfr=72, bmi=29),
        dict(cvd_10a=33.5691, ascvd_10a=22.7763, chd_10a=13.8990, stroke_10a=11.9188, hf_10a=18.3050,
             cvd_30a=None, ascvd_30a=None, chd_30a=None, stroke_30a=None, hf_30a=None),
    ),
    "D doença renal crônica, TFGe 42": (
        dict(sex="F", age=58, tc_mgdl=190, hdl_mgdl=50, sbp=138, diabetes=False,
             smoker=False, antihtn_use=True, statin_use=True, egfr=42, bmi=24),
        dict(cvd_10a=11.6702, ascvd_10a=6.3415, chd_10a=3.0575, stroke_10a=3.5522, hf_10a=6.5660,
             cvd_30a=36.5675, ascvd_30a=20.8350, chd_30a=10.9763, stroke_30a=11.9283, hf_30a=23.3012),
    ),
    "E obesidade grave, IMC 42 (corta só a IC)": (
        dict(sex="M", age=55, tc_mgdl=220, hdl_mgdl=40, sbp=145, diabetes=False,
             smoker=True, antihtn_use=True, statin_use=False, egfr=85, bmi=42),
        dict(cvd_10a=12.8746, ascvd_10a=8.4487, chd_10a=4.9697, stroke_10a=3.6987, hf_10a=None,
             cvd_30a=42.4468, ascvd_30a=28.9466, chd_30a=18.8421, stroke_30a=14.1183, hf_30a=None),
    ),
    "F jovem, perfil normal": (
        dict(sex="F", age=35, tc_mgdl=180, hdl_mgdl=60, sbp=110, diabetes=False,
             smoker=False, antihtn_use=False, statin_use=False, egfr=100, bmi=22),
        dict(cvd_10a=0.3213, ascvd_10a=0.2181, chd_10a=0.0859, stroke_10a=0.1358, hf_10a=0.1242,
             cvd_30a=2.5998, ascvd_30a=1.6231, chd_30a=0.6877, stroke_30a=0.9803, hf_30a=1.1673),
    ),
}


@pytest.mark.parametrize("descricao", list(GOLDEN))
def test_golden_values(descricao):
    entrada, esperado = GOLDEN[descricao]
    obtido = prevent_all(**entrada)
    for campo, alvo in esperado.items():
        if alvo is None:
            assert obtido[campo] is None, f"{descricao}: {campo} deveria vir vazio"
        else:
            assert obtido[campo] == pytest.approx(alvo, abs=1e-4), f"{descricao}: {campo}"


def test_golden_case_e_bate_com_o_mdcalc_em_duas_casas():
    """O que o MDCalc exibiu na tela, arredondado como ele arredonda."""
    entrada, _ = GOLDEN["E obesidade grave, IMC 42 (corta só a IC)"]
    obtido = prevent_all(**entrada)
    esperado_na_tela = {
        "cvd_10a": 12.87, "ascvd_10a": 8.45, "chd_10a": 4.97, "stroke_10a": 3.70,
        "cvd_30a": 42.45, "ascvd_30a": 28.95, "chd_30a": 18.84, "stroke_30a": 14.12,
    }
    for campo, alvo in esperado_na_tela.items():
        assert round(obtido[campo], 2) == alvo, campo
