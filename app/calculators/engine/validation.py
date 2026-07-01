"""Validação de inputs do usuário contra os `calculator_fields` da calculadora."""

from app.calculators.engine.field_coercion import NUMERIC_TYPES, valid_options
from app.models.calculators import CalculatorField


class CalculatorValidationError(Exception):
    """`errors` segue o formato de erros por campo do Pydantic: [{"loc": [...], "msg": "..."}]."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("; ".join(e["msg"] for e in errors))


def validate_inputs(fields: list[CalculatorField], raw_inputs: dict) -> dict:
    """Valida `raw_inputs` contra a definição de campos e retorna os valores convertidos."""
    errors: list[dict] = []
    validated: dict = {}

    def add_error(key: str, msg: str) -> None:
        errors.append({"loc": ["inputs", key], "msg": msg})

    for field in fields:
        value = raw_inputs.get(field.key)

        if value is None:
            if field.required:
                add_error(field.key, "Campo obrigatório ausente")
            continue

        if field.field_type in NUMERIC_TYPES:
            try:
                value = int(value) if field.field_type == "integer" else float(value)
            except (TypeError, ValueError):
                add_error(field.key, "Campo deve ser numérico")
                continue
            if field.min_value is not None and value < field.min_value:
                add_error(field.key, f"Campo abaixo do mínimo ({field.min_value})")
            if field.max_value is not None and value > field.max_value:
                add_error(field.key, f"Campo acima do máximo ({field.max_value})")

        elif field.field_type == "boolean":
            if not isinstance(value, bool):
                add_error(field.key, "Campo deve ser booleano")

        elif field.field_type == "select":
            options = valid_options(field)
            if value not in options:
                add_error(field.key, f"Campo deve ser um dos valores: {sorted(options)}")

        elif field.field_type == "multiselect":
            options = valid_options(field)
            if not isinstance(value, list):
                add_error(field.key, "Campo deve ser uma lista de valores")
            else:
                invalid = [v for v in value if v not in options]
                if invalid:
                    add_error(field.key, f"Valores inválidos {sorted(invalid)}; permitidos: {sorted(options)}")

        elif field.field_type == "text":
            value = str(value)

        validated[field.key] = value

    unknown_keys = set(raw_inputs.keys()) - {f.key for f in fields}
    if unknown_keys:
        add_error("_root_", f"Campos desconhecidos: {sorted(unknown_keys)}")

    if errors:
        raise CalculatorValidationError(errors)

    return validated
