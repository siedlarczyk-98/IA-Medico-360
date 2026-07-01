"""
Golden values do Cockcroft-Gault (Nephron 1976;16:31-41).

CrCl = ((140 - idade) * peso) / (72 * creatinina), x0,85 se feminino.
Peso ideal (Devine): base + 2,3 * (altura_pol - 60), base 50 (M) / 45,5 (F).
Peso ajustado: ideal + 0,4 * (real - ideal).

Valores esperados calculados à mão a partir das fórmulas (independente do código).
"""

import pytest

from app.calculators.formulas.nefrologia.cockcroft_gault import calculate


def _crcl(out: dict) -> float:
    return out["result"]["primary"]["value"]


BASE = dict(idade=60, peso_kg=72, sexo="M", creatinina_mgdl=1.0,
            tipo_peso="real", altura_cm=175)


def test_masculino_peso_real():
    # (140-60)*72 / (72*1.0) = 80.0
    assert _crcl(calculate(BASE)) == pytest.approx(80.0)


def test_feminino_aplica_fator_085():
    out = calculate({**BASE, "sexo": "F"})
    # 80.0 * 0.85 = 68.0
    assert _crcl(out) == pytest.approx(68.0)


def test_masculino_creatinina_alta():
    out = calculate({**BASE, "idade": 40, "peso_kg": 80, "creatinina_mgdl": 1.2})
    # (140-40)*80 / (72*1.2) = 8000/86.4 = 92.59 -> 92.6
    assert _crcl(out) == pytest.approx(92.6, abs=0.05)


def test_peso_ideal_masculino_175cm():
    out = calculate({**BASE, "tipo_peso": "ideal"})
    # ideal = 50 + 2.3*(175/2.54 - 60) = 70.46 -> arredondado 70.5
    assert out["result"]["peso_ideal_kg"] == pytest.approx(70.5, abs=0.1)
    # CrCl com peso ideal: (80*70.4646)/72 = 78.29 -> 78.3
    assert _crcl(out) == pytest.approx(78.3, abs=0.1)


def test_peso_ideal_feminino_160cm():
    out = calculate({**BASE, "sexo": "F", "altura_cm": 160, "tipo_peso": "ideal"})
    # ideal = 45.5 + 2.3*(160/2.54 - 60) = 52.38 -> 52.4
    assert out["result"]["peso_ideal_kg"] == pytest.approx(52.4, abs=0.1)


def test_peso_ajustado():
    out = calculate({**BASE, "peso_kg": 100, "tipo_peso": "ajustado"})
    # ideal 70.4646; ajustado = 70.4646 + 0.4*(100-70.4646) = 82.28
    assert out["result"]["peso_ajustado_kg"] == pytest.approx(82.3, abs=0.1)


def test_alerta_peso_extremo_presente_quando_desvio_maior_20pct():
    out = calculate({**BASE, "peso_kg": 100, "tipo_peso": "real"})
    textos = " ".join(a["text"] for a in out["result"]["alerts"])
    assert "extremo" in textos.lower() or "ajustado" in textos.lower()


def test_alerta_funcao_renal_sempre_presente():
    out = calculate(BASE)
    textos = " ".join(a["text"] for a in out["result"]["alerts"])
    assert "instável" in textos.lower()
