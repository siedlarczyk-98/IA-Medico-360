"""Testes do engine de validação de inputs (app/calculators/engine/validation.py)."""

import pytest

from app.calculators.engine.validation import CalculatorValidationError, validate_inputs
from app.models.calculators import CalculatorField


def make_field(**kwargs) -> CalculatorField:
    defaults = dict(
        key="campo",
        label="Campo",
        field_type="text",
        unit=None,
        required=True,
        min_value=None,
        max_value=None,
        options=None,
        display_order=0,
    )
    defaults.update(kwargs)
    return CalculatorField(**defaults)


def field_errors(exc: CalculatorValidationError) -> dict[str, str]:
    return {e["loc"][-1]: e["msg"] for e in exc.errors}


# --- required ---

def test_campo_obrigatorio_ausente():
    fields = [make_field(key="idade", field_type="number", required=True)]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {})
    assert "idade" in field_errors(exc_info.value)


def test_campo_opcional_ausente_nao_gera_erro():
    fields = [make_field(key="obs", field_type="text", required=False)]
    validated = validate_inputs(fields, {})
    assert validated == {}


# --- number / integer ---

def test_number_convertido_para_float():
    fields = [make_field(key="peso", field_type="number", required=True)]
    validated = validate_inputs(fields, {"peso": "70.5"})
    assert validated["peso"] == 70.5


def test_integer_convertido_para_int():
    fields = [make_field(key="idade", field_type="integer", required=True)]
    validated = validate_inputs(fields, {"idade": "45"})
    assert validated["idade"] == 45
    assert isinstance(validated["idade"], int)


def test_number_invalido_gera_erro():
    fields = [make_field(key="peso", field_type="number", required=True)]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"peso": "abc"})
    assert "peso" in field_errors(exc_info.value)


def test_number_abaixo_do_minimo():
    fields = [make_field(key="idade", field_type="number", required=True, min_value=0)]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"idade": -1})
    assert "idade" in field_errors(exc_info.value)


def test_number_acima_do_maximo():
    fields = [make_field(key="idade", field_type="number", required=True, max_value=120)]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"idade": 121})
    assert "idade" in field_errors(exc_info.value)


def test_number_no_limite_e_valido():
    fields = [make_field(key="idade", field_type="number", required=True, min_value=0, max_value=120)]
    validated = validate_inputs(fields, {"idade": 120})
    assert validated["idade"] == 120


# --- boolean ---

def test_boolean_valido():
    fields = [make_field(key="fumante", field_type="boolean", required=True)]
    validated = validate_inputs(fields, {"fumante": True})
    assert validated["fumante"] is True


def test_boolean_invalido_gera_erro():
    fields = [make_field(key="fumante", field_type="boolean", required=True)]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"fumante": "sim"})
    assert "fumante" in field_errors(exc_info.value)


# --- select ---

def test_select_valor_valido():
    fields = [make_field(key="sexo", field_type="select", required=True, options=[{"value": "M"}, {"value": "F"}])]
    validated = validate_inputs(fields, {"sexo": "M"})
    assert validated["sexo"] == "M"


def test_select_valor_invalido():
    fields = [make_field(key="sexo", field_type="select", required=True, options=[{"value": "M"}, {"value": "F"}])]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"sexo": "X"})
    assert "sexo" in field_errors(exc_info.value)


# --- multiselect ---

def test_multiselect_valores_validos():
    fields = [
        make_field(
            key="comorbidades",
            field_type="multiselect",
            required=True,
            options=[{"value": "dm"}, {"value": "has"}, {"value": "dpoc"}],
        )
    ]
    validated = validate_inputs(fields, {"comorbidades": ["dm", "has"]})
    assert validated["comorbidades"] == ["dm", "has"]


def test_multiselect_nao_e_lista_gera_erro():
    fields = [
        make_field(key="comorbidades", field_type="multiselect", required=True, options=[{"value": "dm"}])
    ]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"comorbidades": "dm"})
    assert "comorbidades" in field_errors(exc_info.value)


def test_multiselect_valor_invalido_na_lista_gera_erro():
    fields = [
        make_field(
            key="comorbidades",
            field_type="multiselect",
            required=True,
            options=[{"value": "dm"}, {"value": "has"}],
        )
    ]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"comorbidades": ["dm", "xyz"]})
    assert "comorbidades" in field_errors(exc_info.value)


def test_multiselect_vazia_e_valida():
    fields = [
        make_field(key="comorbidades", field_type="multiselect", required=False, options=[{"value": "dm"}])
    ]
    validated = validate_inputs(fields, {"comorbidades": []})
    assert validated["comorbidades"] == []


# --- text ---

def test_text_convertido_para_str():
    fields = [make_field(key="obs", field_type="text", required=True)]
    validated = validate_inputs(fields, {"obs": 123})
    assert validated["obs"] == "123"


# --- campos desconhecidos ---

def test_campo_desconhecido_gera_erro():
    fields = [make_field(key="idade", field_type="number", required=False)]
    with pytest.raises(CalculatorValidationError) as exc_info:
        validate_inputs(fields, {"idade": 10, "campo_fantasma": "x"})
    msgs = [e["msg"] for e in exc_info.value.errors]
    assert any("campo_fantasma" in m for m in msgs)


# --- múltiplos campos ---

def test_multiplos_campos_validos_juntos():
    fields = [
        make_field(key="idade", field_type="integer", required=True, min_value=0, max_value=120),
        make_field(key="sexo", field_type="select", required=True, options=[{"value": "M"}, {"value": "F"}]),
        make_field(key="fumante", field_type="boolean", required=False),
    ]
    validated = validate_inputs(fields, {"idade": "60", "sexo": "F", "fumante": False})
    assert validated == {"idade": 60, "sexo": "F", "fumante": False}
