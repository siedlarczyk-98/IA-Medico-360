"""
Cockcroft-Gault — estimativa de clearance de creatinina para ajuste de dose renal.
Referência: Cockcroft DW, Gault MH. Nephron. 1976;16(1):31-41.
"""

from app.calculators.registry import register_formula

_ALERTA_FUNCAO_RENAL_INSTAVEL = (
    "Não usar em função renal instável (IRA em evolução), gestação ou amputações."
)
_ALERTA_PESO_EXTREMO = (
    "Considere usar peso ajustado ou ideal — fórmula pode superestimar/subestimar em "
    "extremos de massa corporal."
)


def _peso_ideal_kg(sexo: str, altura_cm: float) -> float:
    """Fórmula de Devine."""
    altura_pol = altura_cm / 2.54
    base = 50.0 if sexo == "M" else 45.5
    return base + 2.3 * max(altura_pol - 60, 0)


def _peso_ajustado_kg(peso_real: float, peso_ideal: float) -> float:
    return peso_ideal + 0.4 * (peso_real - peso_ideal)


@register_formula("cockcroft_gault_v1")
def calculate(inputs: dict) -> dict:
    idade = int(inputs["idade"])
    peso_real = float(inputs["peso_kg"])
    sexo = inputs["sexo"]  # "F" ou "M"
    creatinina = float(inputs["creatinina_mgdl"])
    tipo_peso = inputs["tipo_peso"]  # "real" | "ideal" | "ajustado"
    altura_cm = float(inputs["altura_cm"])

    peso_ideal = _peso_ideal_kg(sexo, altura_cm)
    peso_ajustado = _peso_ajustado_kg(peso_real, peso_ideal)

    peso_usado = {"real": peso_real, "ideal": peso_ideal, "ajustado": peso_ajustado}[tipo_peso]

    # min_value e dado configuravel em calculator_fields, nao garantia de codigo:
    # sem esta guarda, creatinina 0 derruba a requisicao com ZeroDivisionError.
    if creatinina <= 0:
        raise ValueError("creatinina_mgdl deve ser maior que zero")

    crcl = ((140 - idade) * peso_usado) / (72 * creatinina)
    if sexo == "F":
        crcl *= 0.85
    crcl = round(crcl, 1)

    alerts: list[dict] = []
    if peso_ideal > 0 and abs(peso_real - peso_ideal) / peso_ideal >= 0.20:
        alerts.append({"level": "warning", "text": _ALERTA_PESO_EXTREMO})
    alerts.append({"level": "warning", "text": _ALERTA_FUNCAO_RENAL_INSTAVEL})

    return {
        "result": {
            "primary": {"label": "Clearance de creatinina estimado", "value": crcl, "unit": "mL/min"},
            "peso_usado_kg": round(peso_usado, 1),
            "peso_ideal_kg": round(peso_ideal, 1),
            "peso_ajustado_kg": round(peso_ajustado, 1),
            "alerts": alerts,
        },
        "interpretation": f"CrCl estimado (peso {tipo_peso}): {crcl} mL/min.",
    }
