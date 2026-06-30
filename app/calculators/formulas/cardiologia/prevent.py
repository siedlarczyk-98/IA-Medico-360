"""
Motor PREVENT (AHA) — modelo base, horizontes 10 e 30 anos.
Coeficientes: Khan et al., Circulation 2024, Material Suplementar,
Tabelas S12A (10 anos) e S12F (30 anos).

Validado contra o exemplo numérico publicado no paper (p. 441):
mulher 50a, CT 240 mg/dL, HDL-c 55 mg/dL, sem estatina, PAS tratada 160 mmHg,
sem DM, eGFR 90, IMC 35 → CVD 5,4% / ASCVD 3,6% / HF 2,5% (sem fumo)
                          → ASCVD 6,0% / HF 4,7% (com fumo)

Uso recomendado pela SBC 2025: outcome="ascvd", horizon=10.
"""

import math

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
    sex: "F" ou "M" | age: 30–79 | outcome: "cvd" | "ascvd" | "hf" | horizon: 10 ou 30
    bmi é obrigatório quando outcome="hf".
    """
    coefs = (COEF_10Y if horizon == 10 else COEF_30Y)[outcome][sex]

    tc = tc_mgdl / 38.67
    hdl = hdl_mgdl / 38.67
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
