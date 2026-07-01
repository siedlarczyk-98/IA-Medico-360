"""Utilitários de campo compartilhados entre validação estrita (`validation.py`)
e extração tolerante via IA (`extraction_service.py`), para evitar que as duas
divirjam em como leem `field.options` ou o que conta como tipo numérico.
"""

from app.models.calculators import CalculatorField

NUMERIC_TYPES = {"number", "integer"}


def valid_options(field: CalculatorField) -> set:
    """Conjunto de valores válidos declarados em `field.options` (formato [{value, label}, ...])."""
    return {opt.get("value") for opt in (field.options or []) if isinstance(opt, dict)}
