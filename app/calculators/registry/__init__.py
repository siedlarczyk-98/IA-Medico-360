"""
Registry slug -> função de fórmula.
Cada calculadora `formula` é mapeada pela `formula_key` da sua `calculator_versions`
vigente para uma função pura registrada via @register_formula.
"""

from collections.abc import Callable

FormulaFn = Callable[[dict], dict]

_REGISTRY: dict[str, FormulaFn] = {}


def register_formula(formula_key: str):
    def decorator(fn: FormulaFn) -> FormulaFn:
        if formula_key in _REGISTRY:
            raise ValueError(f"formula_key '{formula_key}' já registrada")
        _REGISTRY[formula_key] = fn
        return fn

    return decorator


def get_formula(formula_key: str) -> FormulaFn:
    fn = _REGISTRY.get(formula_key)
    if fn is None:
        raise KeyError(f"Nenhuma fórmula registrada para formula_key '{formula_key}'")
    return fn
