"""Testes da validação de membro Curseduca (fail-closed) — item 2.1."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.integracoes import curseduca_service


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
        return {"email": "membro@x.com", "groups": [{"name": "[CFM] Cardiologia"}]}

    monkeypatch.setattr(curseduca_service, "_fetch_member", fake_fetch)
    # Devolve o payload, e não um booleano: é dele que sai a especialidade.
    membro = _run(curseduca_service.verify_active_member("membro@x.com"))
    assert membro["email"] == "membro@x.com"


def test_nao_membro_403(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)

    async def fake_fetch(*a, **k):
        return None

    monkeypatch.setattr(curseduca_service, "_fetch_member", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        _run(curseduca_service.verify_active_member("estranho@x.com"))
    assert exc.value.status_code == 403


def test_erro_integracao_falha_fechado_503(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)

    async def fake_fetch(*a, **k):
        raise curseduca_service.CurseducaNotConfigured("api fora do ar")

    monkeypatch.setattr(curseduca_service, "_fetch_member", fake_fetch)
    with pytest.raises(HTTPException) as exc:
        _run(curseduca_service.verify_active_member("a@x.com"))
    assert exc.value.status_code == 503


def test_nomes_de_grupos_tolera_payload_estranho():
    """Payload de terceiro num caminho de LOGIN: nada aqui pode explodir."""
    assert curseduca_service.nomes_de_grupos(None) == []
    assert curseduca_service.nomes_de_grupos({}) == []
    assert curseduca_service.nomes_de_grupos({"groups": None}) == []
    assert curseduca_service.nomes_de_grupos({"groups": "nao-e-lista"}) == []
    assert curseduca_service.nomes_de_grupos({"groups": [{"sem": "nome"}]}) == []
    assert curseduca_service.nomes_de_grupos({"groups": [{"name": 123}]}) == []
    assert curseduca_service.nomes_de_grupos(
        {"groups": [{"name": "Turma"}, {"name": "[CFM] Cardiologia"}]}
    ) == ["Turma", "[CFM] Cardiologia"]


# ── Listagem paginada (sincronização de membros_waid) ──────────────────────


class _ClienteFake:
    def __init__(self, paginas):
        self.paginas = list(paginas)
        self.pedidos = []

    async def get(self, url, params=None, headers=None, timeout=None):
        self.pedidos.append((url, dict(params or {})))
        status, corpo = self.paginas.pop(0)
        return SimpleNamespace(status_code=status, json=lambda: corpo, text=str(corpo))


def test_listagem_percorre_todas_as_paginas(monkeypatch):
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)
    cliente = _ClienteFake([
        (200, {"data": [{"id": 1}, {"id": 2}], "metadata": {"hasMore": True}}),
        (200, {"data": [{"id": 3}], "metadata": {"hasMore": False}}),
    ])
    monkeypatch.setattr(curseduca_service, "get_client", lambda: cliente)

    membros = _run(curseduca_service.listar_membros_do_grupo(120))

    assert [m["id"] for m in membros] == [1, 2, 3]
    assert cliente.pedidos[0][0] == "https://prof.curseduca.pro/groups/120/members"
    assert [p[1]["offset"] for p in cliente.pedidos] == [0, 2]


def test_listagem_com_erro_levanta_em_vez_de_devolver_lista_vazia(monkeypatch):
    """Lista vazia faria a sincronização marcar todo mundo como sem acesso."""
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)
    monkeypatch.setattr(curseduca_service, "get_client", lambda: _ClienteFake([(403, {"message": "x"})]))

    with pytest.raises(curseduca_service.CurseducaNotConfigured):
        _run(curseduca_service.listar_relatorio_de_grupos())


class _ClienteInstavel:
    """Cada item é uma resposta (status, corpo) ou uma exceção a levantar."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = 0

    async def get(self, url, params=None, headers=None, timeout=None):
        self.chamadas += 1
        passo = self.roteiro.pop(0)
        if isinstance(passo, Exception):
            raise passo
        status, corpo = passo
        return SimpleNamespace(status_code=status, json=lambda: corpo, text=str(corpo))


@pytest.fixture
def sem_espera(monkeypatch):
    async def _nada(_segundos):
        return None

    monkeypatch.setattr(curseduca_service.asyncio, "sleep", _nada)
    monkeypatch.setattr(curseduca_service, "get_settings", _settings)


_OK = (200, {"data": [{"id": 1}], "metadata": {"hasMore": False}})


def test_timeout_isolado_e_tentado_de_novo(monkeypatch, sem_espera):
    """O que derrubou a rodada de 2026-10-13: um ReadTimeout num grupo só."""
    import httpx

    cliente = _ClienteInstavel([httpx.ReadTimeout(""), _OK])
    monkeypatch.setattr(curseduca_service, "get_client", lambda: cliente)

    assert _run(curseduca_service.listar_membros_do_grupo(64)) == [{"id": 1}]
    assert cliente.chamadas == 2


def test_erro_5xx_e_tentado_de_novo(monkeypatch, sem_espera):
    cliente = _ClienteInstavel([(502, {}), (503, {}), _OK])
    monkeypatch.setattr(curseduca_service, "get_client", lambda: cliente)

    assert _run(curseduca_service.listar_membros_do_grupo(64)) == [{"id": 1}]


def test_timeout_persistente_desiste(monkeypatch, sem_espera):
    import httpx

    cliente = _ClienteInstavel([httpx.ReadTimeout("")] * 3)
    monkeypatch.setattr(curseduca_service, "get_client", lambda: cliente)

    with pytest.raises(httpx.ReadTimeout):
        _run(curseduca_service.listar_membros_do_grupo(64))
    assert cliente.chamadas == 3


def test_4xx_nao_insiste(monkeypatch, sem_espera):
    """Credencial sem permissão não se resolve tentando de novo."""
    cliente = _ClienteInstavel([(403, {"message": "x"})])
    monkeypatch.setattr(curseduca_service, "get_client", lambda: cliente)

    with pytest.raises(curseduca_service.CurseducaNotConfigured):
        _run(curseduca_service.listar_relatorio_de_grupos())
    assert cliente.chamadas == 1
