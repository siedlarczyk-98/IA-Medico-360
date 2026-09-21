"""
Tetos de infraestrutura da fase de capacidade (varredura de 2026-09-18).

Cada teste trava uma configuração cujo valor ERRADO não quebra nada em
desenvolvimento e derruba o serviço sob carga — o tipo de regressão que só
aparece quando já é incidente.
"""

import asyncio

import redis.asyncio as redis

from app.core import http_client
from app.core.database import engine
from app.services import cache_service


def test_streams_tem_pool_http_proprio():
    """Resposta longa não pode ocupar a conexão de que o login e a triagem precisam."""
    assert http_client.get_stream_client() is not http_client.get_client()
    assert http_client._STREAM_LIMITS.max_connections > http_client._LIMITS.max_connections
    assert http_client._STREAM_TIMEOUT.pool is not None and http_client._STREAM_TIMEOUT.pool <= 5


def test_pool_de_banco_esgotado_falha_rapido():
    # 30 s (o padrão) deixa toda requisição meio minuto pendurada e mantém o pool
    # saturado depois de a causa passar.
    assert engine.pool.timeout() <= 5


def test_redis_usa_pool_bloqueante_com_timeouts():
    cliente = cache_service.novo_cliente_redis("redis://127.0.0.1:1/0")
    pool = cliente.connection_pool

    assert isinstance(pool, redis.BlockingConnectionPool), (
        "pool comum CHEIO levanta erro na hora, que vira cache miss e chamada paga ao modelo"
    )
    assert pool.timeout == cache_service.REDIS_TIMEOUT_S
    assert pool.connection_kwargs["socket_timeout"] == cache_service.REDIS_TIMEOUT_S
    assert pool.connection_kwargs["socket_connect_timeout"] == cache_service.REDIS_TIMEOUT_S


async def test_pharmadb_nao_tem_pool_de_redis_proprio():
    from app.services.integracoes.pharmadb_service import PharmaDBService

    assert await PharmaDBService()._get_redis() is cache_service._get_redis()


# ── Corpo de requisição ──────────────────────────────────────────────────────

async def test_corpo_gigante_e_recusado_pelo_tamanho_declarado_sem_ser_lido(client, user):
    from tests.conftest import auth_headers

    resp = await client.post(
        "/api/v1/orquestrador/stream",
        content=b"x",  # o corpo real é irrelevante: a recusa vem do cabeçalho
        headers={**auth_headers(user), "Content-Type": "application/json", "Content-Length": str(50 * 1024 * 1024)},
    )

    assert resp.status_code == 413
    assert "grande demais" in resp.json()["detail"]


async def test_413_atravessa_o_cors_para_o_app_conseguir_mostrar(client):
    from app.core.config import get_settings

    origem = get_settings().frontend_url
    resp = await client.post(
        "/api/v1/uploads/extract",
        content=b"x",
        headers={"Origin": origem, "Content-Length": str(500 * 1024 * 1024)},
    )

    assert resp.status_code == 413
    assert resp.headers["access-control-allow-origin"] == origem


async def test_upload_tem_teto_proprio_maior_que_o_das_rotas_json():
    from app.core import body_limit

    assert body_limit.LIMITE_UPLOAD > body_limit.MAX_FILE_BYTES
    assert body_limit.LIMITE_GERAL < body_limit.LIMITE_UPLOAD


async def test_requisicao_normal_nao_e_afetada(client):
    assert (await client.get("/api/v1/health")).status_code == 200


# ── PubMed ───────────────────────────────────────────────────────────────────

async def test_cadencia_do_pubmed_espaca_uma_rajada():
    import time

    from app.services.integracoes.pubmed_service import _Cadencia

    cadencia = _Cadencia(por_segundo=50)  # 20 ms entre chamadas
    inicio = time.monotonic()
    await asyncio.gather(*(cadencia.esperar() for _ in range(6)))
    decorrido = time.monotonic() - inicio

    # 6 chamadas = 5 intervalos de 20 ms. Sem cadência seriam ~0 ms.
    assert decorrido >= 0.09, f"a rajada saiu toda de uma vez ({decorrido * 1000:.0f} ms)"


async def test_chamada_isolada_nao_espera():
    import time

    from app.services.integracoes.pubmed_service import _Cadencia

    inicio = time.monotonic()
    await _Cadencia(por_segundo=1).esperar()

    assert time.monotonic() - inicio < 0.05
