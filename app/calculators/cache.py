"""
Cache in-process do catálogo de calculadoras.

Definições e campos mudam apenas por seed/migration, mas eram relidos do banco a
cada request (60 req/min por usuário). O cache guarda os DTOs Pydantic já
montados — nunca instâncias ORM, que não podem ser compartilhadas entre sessões.

Escopo é o processo: com múltiplos workers, cada um tem sua cópia, e a janela de
inconsistência após um seed é de no máximo o TTL.
"""

import time
from typing import TypeVar

from app.core.config import get_settings

settings = get_settings()

T = TypeVar("T")

_entries: dict[str, tuple[float, object]] = {}


def get(key: str) -> object | None:
    entry = _entries.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _entries.pop(key, None)
        return None
    return value


def set_(key: str, value: T) -> T:
    ttl = settings.calculator_catalog_cache_ttl_seconds
    if ttl > 0:
        _entries[key] = (time.monotonic() + ttl, value)
    return value


def clear() -> None:
    """Invalida o catálogo inteiro. Chamar após seeds que alterem definições/campos."""
    _entries.clear()
