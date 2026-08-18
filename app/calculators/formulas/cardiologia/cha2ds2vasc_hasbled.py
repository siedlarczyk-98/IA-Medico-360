"""
CHA2DS2-VASc + HAS-BLED — risco de AVC e risco de sangramento em fibrilação atrial.
Os dois escores são sempre calculados e exibidos juntos (nunca isolados).
Referências: ESC Guidelines for AF management (CHA2DS2-VASc); Pisters et al.,
Chest. 2010;138(5):1093-100 (HAS-BLED).
"""

from app.calculators.registry import register_formula

_ALERTA_SEXO_FEMININO = (
    "Sexo feminino isolado não deve ser interpretado como indicação automática de "
    "anticoagulação."
)
_ALERTA_HASBLED_ISOLADO = (
    "HAS-BLED elevado não deve ser usado isoladamente para negar anticoagulação — "
    "identifica fatores de risco modificáveis."
)


def _interpretacao_chads_vasc(score: int) -> str:
    if score == 0:
        return "Risco muito baixo"
    if score == 1:
        return "Risco baixo a moderado"
    return "Risco moderado a alto"


def _interpretacao_hasbled(score: int) -> str:
    return "Risco de sangramento baixo" if score <= 2 else "Risco de sangramento elevado"


@register_formula("cha2ds2vasc_hasbled_v1")
def calculate(inputs: dict) -> dict:
    idade = int(inputs["idade"])
    sexo = inputs["sexo"]  # "F" ou "M"
    avc_ait_previo = bool(inputs.get("avc_ait_previo"))
    tev_previo = bool(inputs.get("tev_previo"))

    chads = 0
    chads += 1 if inputs.get("icc") else 0
    chads += 1 if inputs.get("hipertensao") else 0
    if idade >= 75:
        chads += 2
    elif idade >= 65:
        chads += 1
    chads += 1 if inputs.get("diabetes") else 0
    chads += 2 if (avc_ait_previo or tev_previo) else 0
    chads += 1 if inputs.get("doenca_vascular") else 0
    chads += 1 if sexo == "F" else 0

    hasbled = 0
    hasbled += 1 if inputs.get("hipertensao_nao_controlada") else 0
    hasbled += 1 if inputs.get("funcao_renal_alterada") else 0
    hasbled += 1 if inputs.get("funcao_hepatica_alterada") else 0
    # Critério "S" do HAS-BLED é especificamente AVC — TEV isolado não conta aqui.
    hasbled += 1 if avc_ait_previo else 0
    hasbled += 1 if inputs.get("sangramento_previo") else 0
    hasbled += 1 if inputs.get("inr_labil") else 0
    hasbled += 1 if idade > 65 else 0
    hasbled += 1 if inputs.get("uso_alcool_drogas") else 0
    hasbled += 1 if inputs.get("medicamentos_predisponentes_sangramento") else 0

    chads_interp = _interpretacao_chads_vasc(chads)
    hasbled_interp = _interpretacao_hasbled(hasbled)

    return {
        "result": {
            "scores": [
                {
                    "key": "chads_vasc",
                    "label": "CHA2DS2-VASc",
                    "value": chads,
                    "max": 9,
                    "interpretation": chads_interp,
                },
                {
                    "key": "has_bled",
                    "label": "HAS-BLED",
                    "value": hasbled,
                    "max": 9,
                    "interpretation": hasbled_interp,
                },
            ],
            "alerts": [
                {"level": "warning", "text": _ALERTA_SEXO_FEMININO},
                {"level": "warning", "text": _ALERTA_HASBLED_ISOLADO},
            ],
        },
        "interpretation": (
            f"CHA2DS2-VASc: {chads} ponto(s) ({chads_interp}). "
            f"HAS-BLED: {hasbled} ponto(s) ({hasbled_interp})."
        ),
    }
