"""
Health checks (item 2.1 do plano de prontidão).

O endpoint antigo respondia "healthy" com o banco fora do ar — a plataforma
não tinha como distinguir aplicação sadia de aplicação incapaz de atender.
"""

import pytest

from app.api.v1.endpoints import health


@pytest.fixture(autouse=True)
def redis_disponivel(monkeypatch):
    """Redis não existe no ambiente de teste; por padrão fingimos que responde."""
    async def _ok():
        return None

    monkeypatch.setattr(health, "_checa_redis", _ok)


# ── Liveness ─────────────────────────────────────────────────────────────

async def test_liveness_responde(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


async def test_liveness_nao_depende_do_banco(client, monkeypatch):
    """
    Liveness precisa responder mesmo com tudo fora do ar: um 503 aqui faz a
    plataforma REINICIAR o container, que é a reação errada para banco caído.
    """
    async def _explode():
        raise RuntimeError("postgres fora do ar")

    monkeypatch.setattr(health, "_checa_postgres", _explode)

    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


# ── Readiness ────────────────────────────────────────────────────────────

async def test_readiness_ok_com_tudo_no_ar(client):
    resp = await client.get("/api/v1/health/ready")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "ready"
    assert corpo["dependencies"]["postgres"]["ok"] is True
    assert corpo["dependencies"]["redis"]["ok"] is True


async def test_readiness_com_banco_fora_do_ar(client, monkeypatch):
    async def _explode():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(health, "_checa_postgres", _explode)

    resp = await client.get("/api/v1/health/ready")

    assert resp.status_code == 503
    corpo = resp.json()
    assert corpo["status"] == "degraded"
    assert corpo["dependencies"]["postgres"]["ok"] is False
    assert corpo["dependencies"]["redis"]["ok"] is True, "Redis está no ar e deve ser reportado assim"


async def test_readiness_com_redis_fora_do_ar(client, monkeypatch):
    async def _explode():
        raise ConnectionError("redis indisponível")

    monkeypatch.setattr(health, "_checa_redis", _explode)

    resp = await client.get("/api/v1/health/ready")

    assert resp.status_code == 503
    assert resp.json()["dependencies"]["redis"]["ok"] is False


async def test_readiness_nao_vaza_detalhe_de_infraestrutura(client, monkeypatch):
    """A resposta é pública: não pode carregar string de conexão nem host."""
    async def _explode():
        raise RuntimeError(
            "could not connect to postgresql://usuario:senha@db-interno.railway:5432/railway"
        )

    monkeypatch.setattr(health, "_checa_postgres", _explode)

    resp = await client.get("/api/v1/health/ready")

    texto = resp.text
    assert "senha" not in texto
    assert "railway" not in texto
    assert "postgresql://" not in texto
    assert resp.json()["dependencies"]["postgres"]["erro"] == "RuntimeError"


async def test_readiness_nao_fica_pendurado(client, monkeypatch):
    """Dependência lenta vira timeout rápido — o health check não pode travar junto."""
    import asyncio

    async def _travado():
        await asyncio.sleep(30)

    monkeypatch.setattr(health, "_checa_redis", _travado)
    monkeypatch.setattr(health, "_TIMEOUT_SEGUNDOS", 0.5)

    import time

    inicio = time.monotonic()
    resp = await client.get("/api/v1/health/ready")
    decorrido = time.monotonic() - inicio

    assert resp.status_code == 503
    assert resp.json()["dependencies"]["redis"]["erro"] == "timeout"
    assert decorrido < 5, f"O health check demorou {decorrido:.1f}s — deveria cortar no timeout"


async def test_readiness_e_publico(client):
    """Sem autenticação: a plataforma consulta antes de haver usuário."""
    assert (await client.get("/api/v1/health/ready")).status_code in (200, 503)
