"""Testes da validação de membro Curseduca (fail-closed) — item 2.1."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import curseduca_service


def _settings(**over):
    base = dict(
        curseduca_validation_enabled=True,
        curseduca_api_base="https://prof.curseduca.pro",
        curseduca_api_key="key",
        curseduca_access_token="tok",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _run(coro):
    return asyncio.run(coro)


def test_desligada_e_noop(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings",
                        lambda: _settings(curseduca_validation_enabled=False))
    # não deve levantar nem chamar a API
    _run(curseduca_service.verify_active_member("qualquer@x.com"))


def test_ligada_sem_credencial_falha_fechado(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings",
                        lambda: _settings(curseduca_api_key=""))
    with pytest.raises(HTTPException) as exc:
        _run(curseduca_service.verify_active_member("a@x.com"))
    assert exc.value.status_code == 503


def test_membro_valido_passa(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)

    async def fake_fetch(*a, **k):
        return True

    monkeypatch.setattr(curseduca_service, "_fetch_member_status", fake_fetch)
    _run(curseduca_service.verify_active_member("membro@x.com"))  # sem exceção


def test_nao_membro_403(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)

    async def fake_fetch(*a, **k):
        return False

    monkeypatch.setattr(curseduca_service, "_fetch_member_status", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        _run(curseduca_service.verify_active_member("estranho@x.com"))
    assert exc.value.status_code == 403


def test_erro_integracao_falha_fechado_503(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)

    async def fake_fetch(*a, **k):
        raise curseduca_service.CurseducaNotConfigured("api fora do ar")

    monkeypatch.setattr(curseduca_service, "_fetch_member_status", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        _run(curseduca_service.verify_active_member("a@x.com"))
    assert exc.value.status_code == 503
