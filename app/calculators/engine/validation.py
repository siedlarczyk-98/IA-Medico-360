"""Validação de inputs do usuário contra os `calculator_fields` da calculadora."""

from app.models.calculators import CalculatorField


class CalculatorValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


_NUMERIC_TYPES = {"number", "integer"}


def validate_inputs(fields: list[CalculatorField], raw_inputs: dict) -> dict:
    """Valida `raw_inputs` contra a definição de campos e retorna os valores convertidos."""
    errors: list[str] = []
    validated: dict = {}

    for field in fields:
        value = raw_inputs.get(field.key)

        if value is None:
            if field.required:
                errors.append(f"Campo obrigatório ausente: {field.key}")
            continue

        if field.field_type in _NUMERIC_TYPES:
            try:
                value = int(value) if field.field_type == "integer" else float(value)
            except (TypeError, ValueError):
                errors.append(f"Campo '{field.key}' deve ser numérico")
                continue
            if field.min_value is not None and value < field.min_value:
                errors.append(f"Campo '{field.key}' abaixo do mínimo ({field.min_value})")
            if field.max_value is not None and value > field.max_value:
                errors.append(f"Campo '{field.key}' acima do máximo ({field.max_value})")

        elif field.field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"Campo '{field.key}' deve ser booleano")

        elif field.field_type == "select":
            valid_options = {opt["value"] for opt in (field.options or [])}
            if value not in valid_options:
                errors.append(f"Campo '{field.key}' deve ser um dos valores: {sorted(valid_options)}")

        elif field.field_type == "text":
            value = str(value)

        validated[field.key] = value

    unknown_keys = set(raw_inputs.keys()) - {f.key for f in fields}
    if unknown_keys:
        errors.append(f"Campos desconhecidos: {sorted(unknown_keys)}")

    if errors:
        raise CalculatorValidationError(errors)

    return validated
