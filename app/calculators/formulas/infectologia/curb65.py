"""
CURB-65 — gravidade de pneumonia adquirida na comunidade.
Referência: Lim WS et al., Thorax. 2003;58(5):377-82.
"""

from app.calculators.registry import register_formula

_UREIA_LIMIAR_MGDL = 42.8  # ~7 mmol/L

_ALERTA_JULGAMENTO_CLINICO = (
    "Interpretação deve considerar contexto social, comorbidades e julgamento clínico — "
    "não é critério isolado de decisão de internação."
)


def _interpretacao(score: int) -> str:
    if score <= 1:
        return "Baixo risco — considerar tratamento ambulatorial"
    if score == 2:
        return "Risco intermediário — considerar internação"
    return "Alto risco — internação, considerar UTI"


@register_formula("curb65_v1")
def calculate(inputs: dict) -> dict:
    confusao = bool(inputs.get("confusao_mental"))
    ureia = float(inputs["ureia_mgdl"])
    fr = int(inputs["fr_irpm"])
    pas = int(inputs["pas_mmhg"])
    pad = int(inputs["pad_mmhg"])
    idade = int(inputs["idade"])

    score = sum([
        confusao,
        ureia > _UREIA_LIMIAR_MGDL,
        fr >= 30,
        pas < 90 or pad <= 60,
        idade >= 65,
    ])

    interp = _interpretacao(score)

    return {
        "result": {
            "primary": {"label": "CURB-65", "value": score, "unit": "pontos"},
            "alerts": [{"level": "warning", "text": _ALERTA_JULGAMENTO_CLINICO}],
        },
        "interpretation": f"CURB-65: {score} ponto(s). {interp}.",
    }
