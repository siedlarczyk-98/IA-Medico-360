"""
Carrega automaticamente todos os módulos de fórmula (organizados por especialidade)
para que os decorators @register_formula sejam executados e populem o registry.
"""

import importlib
import pkgutil

_loaded = False


def load_all_formulas() -> None:
    global _loaded
    if _loaded:
        return
    package = importlib.import_module(__name__)
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{__name__}."):
        importlib.import_module(module_info.name)
    _loaded = True
