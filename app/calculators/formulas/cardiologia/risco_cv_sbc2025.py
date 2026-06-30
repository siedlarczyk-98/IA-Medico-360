"""
Risco Cardiovascular — Diretriz Brasileira de Dislipidemias e Prevenção da Aterosclerose
Referência: Rached et al., Arq Bras Cardiol. 2025;122(9):e20250640 (SBC 2025).

Algoritmo de estratificação: Tabela 4.1 + Figura 4.1 + Seções 3–5.
Motor PREVENT: Khan et al., Circulation 2024 (Tabelas S12A e S12F).
"""

from app.calculators.formulas.cardiologia.prevent import prevent_risk
from app.calculators.registry import register_formula

# ── Risco extremo (Tabela 4.2) ───────────────────────────────────────────────

def _count_major_events(inp: dict) -> int:
    tipos: set = set(inp.get("tipos_evento_cv") or [])
    return sum([
        "sca_recente_12m" in tipos,
        "iam_antigo" in tipos,
        "avc_isquemico" in tipos,
        "dap_sintomatica" in tipos,
    ])


def _count_alto_risco_conditions(inp: dict) -> int:
    """Condições de alto risco da Tabela 4.2 (usadas no critério de risco extremo)."""
    egfr = inp.get("egfr", 100)
    return sum([
        int(inp.get("idade", 0)) >= 65,
        bool(inp.get("hipercolesterolemia_familiar")),
        bool(inp.get("cirurgia_revasc_previa_fora_evento")),
        bool(inp.get("diabetes")),
        bool(inp.get("hipertensao")),
        15 <= egfr <= 59,
        bool(inp.get("fumante")),
        bool(inp.get("ldl_persistente_ge100_max_tto")),
        bool(inp.get("evento_agudo_lt2anos")),
    ])


def _is_extreme_risk(inp: dict) -> bool:
    """Múltiplos eventos CV maiores OU 1 evento + ≥2 condições de alto risco."""
    n = _count_major_events(inp)
    if n == 0:
        return False
    if n >= 2:
        return True
    return _count_alto_risco_conditions(inp) >= 2


# ── Sub-árvore DM (Tabelas 4.5–4.8) ─────────────────────────────────────────

def _dm_renal_risk(egfr: float, albuminuria: float | None) -> str | None:
    """
    Retorna 'alto', 'muito_alto' ou None (usar lógica EAR/EMAR geral).
    Cruzamento TFGe × albuminúria — Tabela 4.7.
    """
    alb = albuminuria if albuminuria is not None else 0.0

    if egfr < 30:           # G4–G5
        return "muito_alto"
    if egfr < 45:           # G3b
        return "alto" if alb < 30 else "muito_alto"
    if egfr < 60:           # G3a
        return "alto" if alb < 300 else "muito_alto"
    if egfr < 90:           # G2
        if alb < 30:
            return None
        return "alto" if alb < 300 else "muito_alto"
    # G1 (≥90)
    if alb < 30:
        return None
    return "alto" if alb < 300 else "muito_alto"


def _dm_ear_list(inp: dict) -> list[str]:
    """Estratificadores de alto risco (EAR) para DM — Tabela 4.6."""
    ear = []
    duracao = inp.get("duracao_dm_anos") or 0
    if duracao > 10:
        ear.append("dm_duracao_gt10a")
    if inp.get("historia_familiar_dac_prematura"):
        ear.append("historia_familiar_dac_prematura")
    if inp.get("sindrome_metabolica"):
        ear.append("sindrome_metabolica")
    if inp.get("hipertensao"):
        ear.append("hipertensao")
    if inp.get("fumante"):
        ear.append("tabagismo_ativo")
    if inp.get("neuropatia_autonoma_incipiente"):
        ear.append("neuropatia_autonoma_incipiente")
    if inp.get("retinopatia_np_leve"):
        ear.append("retinopatia_np_leve")
    # EAR renal
    renal = _dm_renal_risk(inp.get("egfr", 100), inp.get("albuminuria_mg_g"))
    if renal in ("alto", "muito_alto"):
        ear.append("doenca_renal_ear")
    # Aterosclerose subclínica EAR
    cac = inp.get("cac_ua")
    if cac is not None and 10 <= cac <= 300:
        ear.append("cac_10_300")
    if inp.get("placa_carotidea_lt50"):
        ear.append("placa_carotidea_lt50")
    if inp.get("placa_angiotc_lt50"):
        ear.append("placa_angiotc_lt50")
    if inp.get("aaa_conhecido"):
        ear.append("aaa")
    return ear


def _dm_has_emar(inp: dict, ear_count: int) -> bool:
    """Qualquer EMAR (muito alto risco) presente — Tabela 4.8."""
    # ≥3 EAR
    if ear_count >= 3:
        return True
    # DM1 > 20 anos diagnosticado após 18
    if (
        inp.get("tipo_dm") == "dm1"
        and (inp.get("duracao_dm_anos") or 0) > 20
        and inp.get("dm1_diagnosticado_apos_18_anos")
    ):
        return True
    # Estenose > 50% qualquer território
    if inp.get("doenca_aterosclerotica_significativa"):
        return True
    # EMAR renal
    if _dm_renal_risk(inp.get("egfr", 100), inp.get("albuminuria_mg_g")) == "muito_alto":
        return True
    # Hipercolesterolemia grave
    if (inp.get("ct_mgdl") or 0) > 310 or (inp.get("ldl_mgdl") or 0) > 190:
        return True
    # Neuropatia autonômica cardiovascular instalada (2 testes TAC alterados)
    if inp.get("neuropatia_autonoma_instalada"):
        return True
    # Retinopatia moderada-severa/proliferativa ou com evidência de progressão
    if inp.get("retinopatia_avancada"):
        return True
    # EMAR-2: evento CV manifesto prévio
    if inp.get("evento_cv_previo"):
        return True
    return False


def _stratify_dm(inp: dict) -> str:
    """Classificação final para paciente com DM — Tabelas 4.5–4.8."""
    if inp.get("evento_cv_previo") and _is_extreme_risk(inp):
        return "EXTREMO"
    ear = _dm_ear_list(inp)
    if _dm_has_emar(inp, len(ear)):
        return "MUITO_ALTO"
    if len(ear) >= 1:
        return "ALTO"
    # Sem EAR/EMAR — decidir por idade/sexo
    idade = int(inp.get("idade", 0))
    sexo = inp.get("sexo", "M")
    if (sexo == "M" and idade >= 50) or (sexo == "F" and idade >= 56):
        return "ALTO"
    return "INTERMEDIARIO"


# ── Fatores agravantes (Seção 5) ─────────────────────────────────────────────

def _get_fatores_agravantes(inp: dict) -> list[str]:
    """Retorna lista de chaves dos fatores agravantes presentes."""
    fatores = []
    if inp.get("historia_familiar_cv_prematura"):
        fatores.append("historia_familiar_cv_prematura")
    if inp.get("adiposidade_com_param_alterado"):
        fatores.append("adiposidade")
    if inp.get("esteatose_hepatica"):
        fatores.append("esteatose_hepatica")
    if inp.get("sindrome_metabolica"):
        fatores.append("sindrome_metabolica")
    if inp.get("doenca_inflamatoria_cronica"):
        fatores.append("doenca_inflamatoria_cronica")
    if inp.get("transplante_orgao_solido"):
        fatores.append("transplante_orgao_solido")
    if inp.get("fatores_femininos"):
        fatores.append("fatores_femininos")
    lpa = inp.get("lpa_mgdl")
    lpa_nmol = inp.get("lpa_nmol")
    if (lpa is not None and lpa >= 50) or (lpa_nmol is not None and lpa_nmol >= 125):
        fatores.append("lipoproteina_a_elevada")
    if (inp.get("pcr_us_mgL") or 0) >= 2.0:
        fatores.append("pcr_us_elevada")
    return fatores


# ── Labels e metas ───────────────────────────────────────────────────────────

_CATEGORIA_LABELS = {
    "BAIXO":        "Risco Baixo",
    "INTERMEDIARIO": "Risco Intermediário",
    "ALTO":         "Risco Alto",
    "MUITO_ALTO":   "Risco Muito Alto",
    "EXTREMO":      "Risco Extremo",
}

_META_LDL = {
    "BAIXO":        "LDL-c < 130 mg/dL",
    "INTERMEDIARIO": "LDL-c < 100 mg/dL",
    "ALTO":         "LDL-c < 70 mg/dL",
    "MUITO_ALTO":   "LDL-c < 50 mg/dL",
    "EXTREMO":      "LDL-c < 50 mg/dL (idealmente < 40 mg/dL)",
}


# ── Fórmula principal ────────────────────────────────────────────────────────

@register_formula("risco_cv_sbc2025_v1")
def calculate(inputs: dict) -> dict:
    """
    Algoritmo principal de estratificação de risco CV — SBC 2025 (Tabela 4.1 + Figura 4.1).
    Avalia em ordem sequencial; o primeiro critério satisfeito define a categoria.
    """
    inp = inputs
    idade = int(inp["idade"])
    sexo = inp["sexo"]  # "F" ou "M"

    # ── PREVENT (calculado quando dentro da faixa válida, sempre como referência) ──
    prevent_scores: dict = {}
    bmi = inp.get("bmi")
    egfr = float(inp.get("egfr") or 90)
    if 30 <= idade <= 79 and bmi is not None and float(bmi) <= 39.9:
        _kw = dict(
            sex=sexo, age=idade,
            tc_mgdl=float(inp["ct_mgdl"]), hdl_mgdl=float(inp["hdl_mgdl"]),
            sbp=float(inp["sbp_mmhg"]),
            diabetes=bool(inp.get("diabetes")),
            smoker=bool(inp.get("fumante")),
            antihtn_use=bool(inp.get("antihtn_use")),
            statin_use=bool(inp.get("statin_use")),
            egfr=egfr, bmi=float(bmi),
        )
        prevent_scores["ascvd_10a"] = round(prevent_risk(**_kw, outcome="ascvd", horizon=10), 1)
        prevent_scores["cvd_10a"]   = round(prevent_risk(**_kw, outcome="cvd",   horizon=10), 1)
        prevent_scores["hf_10a"]    = round(prevent_risk(**_kw, outcome="hf",    horizon=10), 1)
        if idade <= 59:  # risco 30 anos com sentido clínico apenas para adultos jovens
            prevent_scores["ascvd_30a"] = round(prevent_risk(**_kw, outcome="ascvd", horizon=30), 1)
            prevent_scores["cvd_30a"]   = round(prevent_risk(**_kw, outcome="cvd",   horizon=30), 1)

    categoria: str | None = None
    passo: int | None = None

    # ── Passo 1: evento CV aterosclerótico prévio? ───────────────────────────
    if inp.get("evento_cv_previo"):
        if _is_extreme_risk(inp):
            categoria, passo = "EXTREMO", 1
        else:
            categoria, passo = "MUITO_ALTO", 1

    # ── Passo 2: doença aterosclerótica significativa / CAC > 300 ────────────
    if categoria is None:
        cac = inp.get("cac_ua")
        if inp.get("doenca_aterosclerotica_significativa") or (cac is not None and float(cac) > 300):
            categoria, passo = "MUITO_ALTO", 2

    # ── Passo 3: diabetes mellitus ───────────────────────────────────────────
    if categoria is None and inp.get("diabetes"):
        categoria = _stratify_dm(inp)
        passo = 3

    # ── Passo 4: marcadores de aterosclerose subclínica / LDL ≥ 190 / Lp(a) > 180 ──
    if categoria is None:
        cac = inp.get("cac_ua")
        lpa = inp.get("lpa_mgdl")
        lpa_nmol = inp.get("lpa_nmol")
        ldl = float(inp.get("ldl_mgdl") or 0)
        hf = bool(inp.get("hipercolesterolemia_familiar"))
        cac_val = float(cac) if cac is not None else None

        # HF + CAC > 100 → MUITO ALTO (Tabela 4.4)
        if hf and cac_val is not None and cac_val > 100:
            categoria, passo = "MUITO_ALTO", 4
        elif (
            inp.get("placa_carotidea_lt50")
            or inp.get("placa_angiotc_lt50")
            or inp.get("aaa_conhecido")
            or ldl >= 190
            or (lpa is not None and float(lpa) > 180)
            or (lpa_nmol is not None and float(lpa_nmol) > 390)
            or (cac_val is not None and cac_val > 100)
            or bool(inp.get("cac_percentil_gt75"))
        ):
            categoria, passo = "ALTO", 4

    # ── Passo 5: PREVENT + LDL + fatores agravantes ─────────────────────────
    if categoria is None:
        risco_10a = prevent_scores.get("ascvd_10a")
        ldl = float(inp.get("ldl_mgdl") or 0)
        fatores = _get_fatores_agravantes(inp)
        tem_fator = len(fatores) > 0

        if risco_10a is None:
            # Fora da faixa PREVENT (< 30a ou > 79a, ou BMI > 39,9 ou dados ausentes)
            categoria = "INTERMEDIARIO" if tem_fator else "BAIXO"
            passo = 5
        elif risco_10a >= 20:
            categoria, passo = "ALTO", 5
        elif risco_10a >= 5:
            categoria = "ALTO" if tem_fator else "INTERMEDIARIO"
            passo = 5
        else:
            # < 5%
            if 160 <= ldl < 190:
                categoria, passo = "INTERMEDIARIO", 5
            elif tem_fator:
                categoria, passo = "INTERMEDIARIO", 5
            else:
                categoria, passo = "BAIXO", 5

    # Fatores agravantes sempre calculados (contexto clínico)
    fatores_agravantes = _get_fatores_agravantes(inp)

    meta = _META_LDL.get(categoria, "")
    label = _CATEGORIA_LABELS.get(categoria, categoria)

    return {
        "result": {
            "categoria": categoria,
            "prevent": prevent_scores,
            "passo_determinante": passo,
            "fatores_agravantes": fatores_agravantes,
            "meta_ldl_recomendada": meta,
        },
        "interpretation": f"{label} — Meta de LDL-c: {meta}.",
    }
