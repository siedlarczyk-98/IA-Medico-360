"""
Motor PREVENT (AHA) — modelo base, cinco desfechos, horizontes 10 e 30 anos.
Coeficientes: Khan et al., Circulation 2024, Material Suplementar,
Tabelas S12A (10 anos) e S12F (30 anos) — os 398 conferidos um a um contra a
planilha suplementar. Desfechos: cvd (DCV total), ascvd, hf (insuficiência
cardíaca), chd (doença coronariana) e stroke (AVC).

O pacote R oficial da AHA (`AHAprevent`) só expõe cvd/ascvd/hf; coronariana e
AVC saem apenas da planilha do paper. O MDCalc exibe cvd/ascvd/chd/stroke e
omite hf — aqui entregamos os cinco.

Validado contra o exemplo numérico publicado no paper (p. 441):
mulher 50a, CT 240 mg/dL, HDL-c 55 mg/dL, sem estatina, PAS tratada 160 mmHg,
sem DM, eGFR 90, IMC 35 → CVD 5,4% / ASCVD 3,6% / HF 2,5% (sem fumo)
                          → ASCVD 6,0% / HF 4,7% (com fumo)

Uso recomendado pela SBC 2025: outcome="ascvd", horizon=10.
"""

import math
from collections.abc import Callable
from typing import NamedTuple

# ── Tabela S12A (10 anos) ────────────────────────────────────────────────────

COEF_10Y: dict = {
    "cvd": {
        "F": dict(age10=0.7939329, nonhdl=0.0305239, hdl=-0.1606857, sbp_lt110=-0.2394003,
                  sbp_ge110=0.3600781, dm=0.8667604, smoke=0.5360739, egfr_lt60=0.6045917,
                  egfr_ge60=0.0433769, htntx=0.3151672, statin=-0.1477655, tx_sbp_ge110=-0.0663612,
                  tx_nonhdl=0.1197879, age_nonhdl=-0.0819715, age_hdl=0.0306769,
                  age_sbp_ge110=-0.0946348, age_dm=-0.27057, age_smoke=-0.078715,
                  age_egfr_lt60=-0.1637806, const=-3.307728),
        "M": dict(age10=0.7688528, nonhdl=0.0736174, hdl=-0.0954431, sbp_lt110=-0.4347345,
                  sbp_ge110=0.3362658, dm=0.7692857, smoke=0.4386871, egfr_lt60=0.5378979,
                  egfr_ge60=0.0164827, htntx=0.288879, statin=-0.1337349, tx_sbp_ge110=-0.0475924,
                  tx_nonhdl=0.150273, age_nonhdl=-0.0517874, age_hdl=0.0191169,
                  age_sbp_ge110=-0.1049477, age_dm=-0.2251948, age_smoke=-0.0895067,
                  age_egfr_lt60=-0.1543702, const=-3.031168),
    },
    "ascvd": {
        "F": dict(age10=0.719883, nonhdl=0.1176967, hdl=-0.151185, sbp_lt110=-0.0835358,
                  sbp_ge110=0.3592852, dm=0.8348585, smoke=0.4831078, egfr_lt60=0.4864619,
                  egfr_ge60=0.0397779, htntx=0.2265309, statin=-0.0592374, tx_sbp_ge110=-0.0395762,
                  tx_nonhdl=0.0844423, age_nonhdl=-0.0567839, age_hdl=0.0325692,
                  age_sbp_ge110=-0.1035985, age_dm=-0.2417542, age_smoke=-0.0791142,
                  age_egfr_lt60=-0.1671492, const=-3.819975),
        "M": dict(age10=0.7099847, nonhdl=0.1658663, hdl=-0.1144285, sbp_lt110=-0.2837212,
                  sbp_ge110=0.3239977, dm=0.7189597, smoke=0.3956973, egfr_lt60=0.3690075,
                  egfr_ge60=0.0203619, htntx=0.2036522, statin=-0.0865581, tx_sbp_ge110=-0.0322916,
                  tx_nonhdl=0.114563, age_nonhdl=-0.0300005, age_hdl=0.0232747,
                  age_sbp_ge110=-0.0927024, age_dm=-0.2018525, age_smoke=-0.0970527,
                  age_egfr_lt60=-0.1217081, const=-3.500655),
    },
    "hf": {
        "F": dict(age10=0.8998235, sbp_lt110=-0.4559771, sbp_ge110=0.3576505, dm=1.038346,
                  smoke=0.583916, bmi_lt30=-0.0072294, bmi_ge30=0.2997706, egfr_lt60=0.7451638,
                  egfr_ge60=0.0557087, htntx=0.3534442, tx_sbp_ge110=-0.0981511,
                  age_sbp_ge110=-0.0946663, age_dm=-0.3581041, age_smoke=-0.1159453,
                  age_bmi_ge30=-0.003878, age_egfr_lt60=-0.1884289, const=-4.310409),
        "M": dict(age10=0.8972642, sbp_lt110=-0.6811466, sbp_ge110=0.3634461, dm=0.923776,
                  smoke=0.5023736, bmi_lt30=-0.0485841, bmi_ge30=0.3726929, egfr_lt60=0.6926917,
                  egfr_ge60=0.0251827, htntx=0.2980922, tx_sbp_ge110=-0.0497731,
                  age_sbp_ge110=-0.1289201, age_dm=-0.3040924, age_smoke=-0.1401688,
                  age_bmi_ge30=0.0068126, age_egfr_lt60=-0.1797778, const=-3.946391),
    },
    "chd": {
        "F": dict(age10=0.7587146, nonhdl=0.1810949, hdl=-0.2014507, sbp_lt110=-0.0881827,
                  sbp_ge110=0.3547731, dm=0.9045358, smoke=0.5410917, egfr_lt60=0.5198725,
                  egfr_ge60=0.0325935, htntx=0.2010642, statin=-0.036195, tx_sbp_ge110=-0.0891238,
                  tx_nonhdl=0.0750716, age_nonhdl=-0.0683256, age_hdl=0.0484755,
                  age_sbp_ge110=-0.0898086, age_dm=-0.2569041, age_smoke=-0.0786607,
                  age_egfr_lt60=-0.1597513, const=-4.608751),
        "M": dict(age10=0.7423283, nonhdl=0.2572109, hdl=-0.1820374, sbp_lt110=-0.3174515,
                  sbp_ge110=0.312778, dm=0.7485249, smoke=0.3912047, egfr_lt60=0.376487,
                  egfr_ge60=0.0193687, htntx=0.1588199, statin=-0.0494555, tx_sbp_ge110=-0.0577851,
                  tx_nonhdl=0.0809765, age_nonhdl=-0.0517872, age_hdl=0.0489033,
                  age_sbp_ge110=-0.0850404, age_dm=-0.2107552, age_smoke=-0.1206397,
                  age_egfr_lt60=-0.07795, const=-4.156753),
    },
    "stroke": {
        "F": dict(age10=0.6907849, nonhdl=0.0534279, hdl=-0.1055109, sbp_lt110=-0.113078,
                  sbp_ge110=0.3665217, dm=0.8013721, smoke=0.4187039, egfr_lt60=0.4539767,
                  egfr_ge60=0.0515087, htntx=0.2494624, statin=-0.0798829, tx_sbp_ge110=-0.0079039,
                  tx_nonhdl=0.0833101, age_nonhdl=-0.0409242, age_hdl=0.016994,
                  age_sbp_ge110=-0.1191213, age_dm=-0.2480549, age_smoke=-0.0998063,
                  age_egfr_lt60=-0.1759075, const=-4.409199),
        "M": dict(age10=0.722513, nonhdl=0.0263348, hdl=-0.0248959, sbp_lt110=-0.268104,
                  sbp_ge110=0.3474634, dm=0.684699, smoke=0.3874844, egfr_lt60=0.3877827,
                  egfr_ge60=0.0201965, htntx=0.232963, statin=-0.1178935, tx_sbp_ge110=0.0120926,
                  tx_nonhdl=0.155739, age_nonhdl=0.0141928, age_hdl=-0.0111745,
                  age_sbp_ge110=-0.1155391, age_dm=-0.2123743, age_smoke=-0.0824133,
                  age_egfr_lt60=-0.180789, const=-4.20881),
    },
}

# ── Tabela S12F (30 anos) ────────────────────────────────────────────────────

COEF_30Y: dict = {
    "cvd": {
        "F": dict(age10=0.5503079, age2=-0.0928369, nonhdl=0.0409794, hdl=-0.1663306,
                  sbp_lt110=-0.1628654, sbp_ge110=0.3299505, dm=0.6793894, smoke=0.3196112,
                  egfr_lt60=0.1857101, egfr_ge60=0.0553528, htntx=0.2894, statin=-0.075688,
                  tx_sbp_ge110=-0.056367, tx_nonhdl=0.1071019, age_nonhdl=-0.0751438,
                  age_hdl=0.0301786, age_sbp_ge110=-0.0998776, age_dm=-0.3206166,
                  age_smoke=-0.1607862, age_egfr_lt60=-0.1450788, const=-1.318827),
        "M": dict(age10=0.4627309, age2=-0.0984281, nonhdl=0.0836088, hdl=-0.1029824,
                  sbp_lt110=-0.2140352, sbp_ge110=0.2904325, dm=0.5331276, smoke=0.2141914,
                  egfr_lt60=0.1155556, egfr_ge60=0.0603775, htntx=0.232714, statin=-0.0272112,
                  tx_sbp_ge110=-0.0384488, tx_nonhdl=0.134192, age_nonhdl=-0.0511759,
                  age_hdl=0.0165865, age_sbp_ge110=-0.1101437, age_dm=-0.2585943,
                  age_smoke=-0.1566406, age_egfr_lt60=-0.1166776, const=-1.148204),
    },
    "ascvd": {
        "F": dict(age10=0.4669202, age2=-0.0893118, nonhdl=0.1256901, hdl=-0.1542255,
                  sbp_lt110=-0.0018093, sbp_ge110=0.322949, dm=0.6296707, smoke=0.268292,
                  egfr_lt60=0.100106, egfr_ge60=0.0499663, htntx=0.1875292, statin=0.0152476,
                  tx_sbp_ge110=-0.0276123, tx_nonhdl=0.0736147, age_nonhdl=-0.0521962,
                  age_hdl=0.0316918, age_sbp_ge110=-0.1046101, age_dm=-0.2727793,
                  age_smoke=-0.1530907, age_egfr_lt60=-0.1299149, const=-1.974074),
        "M": dict(age10=0.3994099, age2=-0.0937484, nonhdl=0.1744643, hdl=-0.120203,
                  sbp_lt110=-0.0665117, sbp_ge110=0.2753037, dm=0.4790257, smoke=0.1782635,
                  egfr_lt60=-0.0218789, egfr_ge60=0.0602553, htntx=0.1421182, statin=0.0135996,
                  tx_sbp_ge110=-0.0218265, tx_nonhdl=0.1013148, age_nonhdl=-0.0312619,
                  age_hdl=0.020673, age_sbp_ge110=-0.0920935, age_dm=-0.2159947,
                  age_smoke=-0.1548811, age_egfr_lt60=-0.0712547, const=-1.736444),
    },
    "hf": {
        "F": dict(age10=0.6254374, age2=-0.0983038, sbp_lt110=-0.3919241, sbp_ge110=0.3142295,
                  dm=0.8330787, smoke=0.3438651, bmi_lt30=0.0594874, bmi_ge30=0.2525536,
                  egfr_lt60=0.2981642, egfr_ge60=0.0667159, htntx=0.333921, tx_sbp_ge110=-0.0893177,
                  age_sbp_ge110=-0.0974299, age_dm=-0.404855, age_smoke=-0.1982991,
                  age_bmi_ge30=-0.0035619, age_egfr_lt60=-0.1564215, const=-2.205379),
        "M": dict(age10=0.5681541, age2=-0.1048388, sbp_lt110=-0.4761564, sbp_ge110=0.30324,
                  dm=0.6840338, smoke=0.2656273, bmi_lt30=0.0833107, bmi_ge30=0.26999,
                  egfr_lt60=0.2541805, egfr_ge60=0.0638923, htntx=0.2583631, tx_sbp_ge110=-0.0391938,
                  age_sbp_ge110=-0.1269124, age_dm=-0.3273572, age_smoke=-0.2043019,
                  age_bmi_ge30=-0.0182831, age_egfr_lt60=-0.1342618, const=-1.95751),
    },

    "chd": {
        "F": dict(age10=0.4912423, age2=-0.0917078, nonhdl=0.1878256, hdl=-0.2035703,
                  sbp_lt110=-0.0030222, sbp_ge110=0.3111757, dm=0.6803247, smoke=0.3215313,
                  egfr_lt60=0.1252615, egfr_ge60=0.0414579, htntx=0.1561303, statin=0.0384138,
                  tx_sbp_ge110=-0.0795531, tx_nonhdl=0.0635262, age_nonhdl=-0.0637665,
                  age_hdl=0.0474074, age_sbp_ge110=-0.0876484, age_dm=-0.2803099,
                  age_smoke=-0.1513626, age_egfr_lt60=-0.1130454, const=-2.733866),
        "M": dict(age10=0.4171209, age2=-0.0949994, nonhdl=0.2651913, hdl=-0.1879446,
                  sbp_lt110=-0.0971746, sbp_ge110=0.258931, dm=0.4956463, smoke=0.1728844,
                  egfr_lt60=-0.0091955, egfr_ge60=0.0578155, htntx=0.0939196, statin=0.0508921,
                  tx_sbp_ge110=-0.0486024, tx_nonhdl=0.0669478, age_nonhdl=-0.0533361,
                  age_hdl=0.0461425, age_sbp_ge110=-0.0812234, age_dm=-0.216315,
                  age_smoke=-0.1749197, age_egfr_lt60=-0.0241467, const=-2.376762),
    },
    "stroke": {
        "F": dict(age10=0.4366978, age2=-0.0873673, nonhdl=0.0586334, hdl=-0.1069016,
                  sbp_lt110=-0.0317106, sbp_ge110=0.3272741, dm=0.5841726, smoke=0.2045681,
                  egfr_lt60=0.0765812, egfr_ge60=0.0603226, htntx=0.2087816, statin=-0.0095137,
                  tx_sbp_ge110=0.0014436, tx_nonhdl=0.0720012, age_nonhdl=-0.0361779,
                  age_hdl=0.015888, age_sbp_ge110=-0.1179062, age_dm=-0.2710221,
                  age_smoke=-0.1702836, age_egfr_lt60=-0.1320992, const=-2.62078),
        "M": dict(age10=0.4003448, age2=-0.0935927, nonhdl=0.0309419, hdl=-0.0280763,
                  sbp_lt110=-0.047704, sbp_ge110=0.2925734, dm=0.4236823, smoke=0.1675238,
                  egfr_lt60=-0.0009216, egfr_ge60=0.0575221, htntx=0.1685514, statin=-0.020829,
                  tx_sbp_ge110=0.0230042, tx_nonhdl=0.1413652, age_nonhdl=0.0145411,
                  age_hdl=-0.0149606, age_sbp_ge110=-0.1118468, age_dm=-0.2152953,
                  age_smoke=-0.1339295, age_egfr_lt60=-0.1225081, const=-2.458022),
    },
}


def prevent_risk(
    sex: str,
    age: int,
    tc_mgdl: float,
    hdl_mgdl: float,
    sbp: float,
    diabetes: bool,
    smoker: bool,
    antihtn_use: bool,
    statin_use: bool,
    egfr: float,
    bmi: float | None = None,
    outcome: str = "ascvd",
    horizon: int = 10,
) -> float:
    """
    Retorna risco em % (float).
    sex: "F" ou "M" | age: 30–79 | horizon: 10 ou 30
    outcome: "cvd" | "ascvd" | "hf" | "chd" | "stroke"
    bmi é obrigatório quando outcome="hf" — é o único que usa IMC.
    """
    coefs = (COEF_10Y if horizon == 10 else COEF_30Y)[outcome][sex]

    # Multiplicação por 0,02586, e não divisão por 38,67: é exatamente o que a
    # `mmol_conversion` da AHA faz. As duas constantes diferem em 7e-6 relativo,
    # o que vira ±0,1 no valor exibido em ~1 a cada 5.700 combinações de entrada.
    tc = 0.02586 * tc_mgdl
    hdl = 0.02586 * hdl_mgdl
    nonhdl = (tc - hdl) - 3.5
    hdl_c = (hdl - 1.3) / 0.3
    agec = (age - 55) / 10
    sbp_lt110 = (min(sbp, 110) - 110) / 20
    sbp_ge110 = (max(sbp, 110) - 130) / 20
    egfr_lt60 = (60 - min(egfr, 60)) / 15
    egfr_ge60 = (90 - max(egfr, 60)) / 15
    dm = int(diabetes)
    smoke = int(smoker)
    htntx = int(antihtn_use)
    statin = int(statin_use)

    logit = coefs["const"]
    logit += coefs["age10"] * agec
    if horizon == 30:
        logit += coefs["age2"] * agec ** 2
    if "nonhdl" in coefs:
        logit += coefs["nonhdl"] * nonhdl
        logit += coefs["age_nonhdl"] * agec * nonhdl
        logit += coefs["tx_nonhdl"] * nonhdl * statin
    if "hdl" in coefs:
        logit += coefs["hdl"] * hdl_c
        logit += coefs["age_hdl"] * agec * hdl_c
    logit += coefs["sbp_lt110"] * sbp_lt110
    logit += coefs["sbp_ge110"] * sbp_ge110
    logit += coefs["age_sbp_ge110"] * agec * sbp_ge110
    logit += coefs["tx_sbp_ge110"] * sbp_ge110 * htntx
    logit += coefs["dm"] * dm
    logit += coefs["age_dm"] * agec * dm
    logit += coefs["smoke"] * smoke
    logit += coefs["age_smoke"] * agec * smoke
    logit += coefs["egfr_lt60"] * egfr_lt60
    logit += coefs["egfr_ge60"] * egfr_ge60
    logit += coefs["age_egfr_lt60"] * agec * egfr_lt60
    logit += coefs["htntx"] * htntx
    if "statin" in coefs:
        logit += coefs["statin"] * statin
    if outcome == "hf":
        if bmi is None:
            raise ValueError("bmi é obrigatório para outcome='hf'")
        bmi_lt30 = (min(bmi, 30) - 25) / 5
        bmi_ge30 = (max(bmi, 30) - 30) / 5
        logit += coefs["bmi_lt30"] * bmi_lt30
        logit += coefs["bmi_ge30"] * bmi_ge30
        logit += coefs["age_bmi_ge30"] * agec * bmi_ge30

    return 1 / (1 + math.exp(-logit)) * 100


# ── Faixas de validade (AHAprevent::pred_risk_base) ──────────────────────────
# A AHA invalida por desfecho, não em bloco: cada variável só derruba os
# desfechos cuja equação a usa. IMC, por exemplo, só entra no HF — um paciente
# com IMC 42 continua tendo ASCVD e CVD válidos.
#
# A tabela `_REGRAS` é a fonte única: dela saem tanto os campos anulados quanto
# a explicação mostrada ao médico. Elas não podem divergir — uma célula vazia
# sem justificativa na tela é indistinguível de bug.

# Coronariana e AVC usam lipídios e não usam IMC, então acompanham CVD/ASCVD.
_LIPIDICOS = (
    "cvd_10a", "ascvd_10a", "chd_10a", "stroke_10a",
    "cvd_30a", "ascvd_30a", "chd_30a", "stroke_30a",
)
_HF = ("hf_10a", "hf_30a")
_TODOS = _LIPIDICOS + _HF
_TRINTA_ANOS = tuple(c for c in _TODOS if c.endswith("_30a"))


class RegraDeFaixa(NamedTuple):
    codigo: str
    desfechos: tuple[str, ...]
    mensagem: str
    fora_da_faixa: Callable[[dict], bool]


_REGRAS: tuple[RegraDeFaixa, ...] = (
    RegraDeFaixa(
        "idade_fora_30_79", _TODOS,
        "O PREVENT é validado para pacientes de 30 a 79 anos. Fora dessa faixa "
        "nenhum risco é calculado.",
        lambda v: not 30 <= v["age"] <= 79,
    ),
    RegraDeFaixa(
        "idade_acima_59", _TRINTA_ANOS,
        "O horizonte de 30 anos é validado apenas dos 30 aos 59 anos. Acima "
        "disso a AHA não calcula projeção de 30 anos — o risco em 10 anos "
        "permanece válido.",
        lambda v: 30 <= v["age"] <= 79 and v["age"] > 59,
    ),
    RegraDeFaixa(
        "ct_fora_130_320", _LIPIDICOS,
        "Colesterol total fora da faixa de validação (130 a 320 mg/dL). Os "
        "desfechos de DCV e ASCVD dependem dele; a insuficiência cardíaca não.",
        lambda v: not 130 <= v["tc_mgdl"] <= 320,
    ),
    RegraDeFaixa(
        "hdl_fora_20_100", _LIPIDICOS,
        "HDL-c fora da faixa de validação (20 a 100 mg/dL). Os desfechos de DCV "
        "e ASCVD dependem dele; a insuficiência cardíaca não.",
        lambda v: not 20 <= v["hdl_mgdl"] <= 100,
    ),
    RegraDeFaixa(
        "pas_fora_90_200", _TODOS,
        "Pressão arterial sistólica fora da faixa de validação (90 a 200 mmHg). "
        "Ela entra em todas as equações, então nenhum risco é calculado.",
        lambda v: not 90 <= v["sbp"] <= 200,
    ),
    RegraDeFaixa(
        "egfr_nao_positiva", _TODOS,
        "TFGe precisa ser maior que zero. Ela entra em todas as equações, então "
        "nenhum risco é calculado.",
        lambda v: v["egfr"] <= 0,
    ),
    RegraDeFaixa(
        "imc_fora_18_5_39_9", _HF,
        "IMC fora da faixa de validação (18,5 a 39,9 kg/m²). Só as equações de "
        "insuficiência cardíaca usam IMC — DCV e ASCVD seguem válidos.",
        lambda v: not 18.5 <= v["bmi"] < 40,
    ),
)


def _regras_violadas(valores: dict) -> list[RegraDeFaixa]:
    return [r for r in _REGRAS if r.fora_da_faixa(valores)]


def prevent_all(
    sex: str,
    age: int,
    tc_mgdl: float,
    hdl_mgdl: float,
    sbp: float,
    diabetes: bool,
    smoker: bool,
    antihtn_use: bool,
    statin_use: bool,
    egfr: float,
    bmi: float,
) -> dict[str, float | None]:
    """
    Os seis desfechos do modelo base, com as regras de faixa da AHA aplicadas
    desfecho a desfecho. `None` onde a AHA devolve NA. Não arredonda.
    """
    comuns = dict(
        sex=sex, age=age, tc_mgdl=tc_mgdl, hdl_mgdl=hdl_mgdl, sbp=sbp,
        diabetes=diabetes, smoker=smoker, antihtn_use=antihtn_use,
        statin_use=statin_use, egfr=egfr, bmi=bmi,
    )
    invalidos = {campo for regra in _regras_violadas(comuns) for campo in regra.desfechos}
    return {
        campo: None if campo in invalidos else prevent_risk(
            **comuns, outcome=campo[:-4], horizon=int(campo[-3:-1])
        )
        for campo in _TODOS
    }


def prevent_avisos(
    sex: str,
    age: int,
    tc_mgdl: float,
    hdl_mgdl: float,
    sbp: float,
    diabetes: bool,
    smoker: bool,
    antihtn_use: bool,
    statin_use: bool,
    egfr: float,
    bmi: float,
) -> list[dict]:
    """
    Por que cada desfecho ficou de fora, na ordem em que as regras são avaliadas.
    Vazio quando o paciente está dentro de todas as faixas.
    """
    comuns = dict(
        sex=sex, age=age, tc_mgdl=tc_mgdl, hdl_mgdl=hdl_mgdl, sbp=sbp,
        diabetes=diabetes, smoker=smoker, antihtn_use=antihtn_use,
        statin_use=statin_use, egfr=egfr, bmi=bmi,
    )
    return [
        {"codigo": r.codigo, "mensagem": r.mensagem, "desfechos": list(r.desfechos)}
        for r in _regras_violadas(comuns)
    ]
