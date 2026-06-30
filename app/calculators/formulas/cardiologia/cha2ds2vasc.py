"""CHA2DS2-VASc — risco de AVC em fibrilação atrial não valvar."""

from app.calculators.registry import register_formula

_AGE_POINTS = {"menor_65": 0, "65_a_74": 1, "75_mais": 2}


def _interpret(score: int) -> str:
    if score == 0:
        return "Risco muito baixo"
    if score == 1:
        return "Risco baixo"
    return "Risco moderado a alto — considerar anticoagulação"


@register_formula("cha2ds2vasc_v1")
def calculate(inputs: dict) -> dict:
    score = _AGE_POINTS[inputs["faixa_etaria"]]
    score += 1 if inputs["sexo_feminino"] else 0
    score += 1 if inputs["icc"] else 0
    score += 1 if inputs["hipertensao"] else 0
    score += 2 if inputs["avc_previo"] else 0
    score += 1 if inputs["doenca_vascular"] else 0
    score += 1 if inputs["diabetes"] else 0

    return {
        "result": {"score": score},
        "interpretation": _interpret(score),
    }
