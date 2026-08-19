"""
Log estruturado e correlação por requisição (item 2.3 do plano de prontidão).

Duas garantias:
  1. Toda requisição tem um id, devolvido no header e presente em cada linha
     de log — é o que liga um erro no Sentry ao rastro no Phoenix.
  2. O log NÃO carrega conteúdo clínico. Correlação por id, nunca por prompt.
"""

import json
import logging

from app.core.logging_config import (
    HEADER_REQUEST_ID,
    JsonFormatter,
    request_id_var,
    setup_logging,
)


def _formata(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(msg: str, **extra) -> logging.LogRecord:
    r = logging.LogRecord("app.teste", logging.INFO, "arquivo.py", 10, msg, (), None)
    r.__dict__.update(extra)
    return r


# ── Formato ──────────────────────────────────────────────────────────────

def test_linha_de_log_e_json_valido():
    saida = _formata(_record("consulta processada"))

    assert saida["level"] == "INFO"
    assert saida["logger"] == "app.teste"
    assert saida["message"] == "consulta processada"
    assert "timestamp" in saida


def test_campos_extras_entram_no_json():
    saida = _formata(_record("custo registrado", model_id="claude-sonnet-4-6", custo_usd=0.03))

    assert saida["model_id"] == "claude-sonnet-4-6"
    assert saida["custo_usd"] == 0.03


def test_excecao_e_serializada():
    try:
        raise ValueError("provider timeout")
    except ValueError:
        import sys

        r = logging.LogRecord("app.teste", logging.ERROR, "f.py", 1, "falhou", (), sys.exc_info())

    saida = _formata(r)
    assert "provider timeout" in saida["exception"]


def test_mensagem_com_acento_nao_e_escapada():
    saida = _formata(_record("interação salva"))
    assert saida["message"] == "interação salva"


# ── Correlação ───────────────────────────────────────────────────────────

def test_request_id_aparece_na_linha():
    token = request_id_var.set("abc123")
    try:
        assert _formata(_record("qualquer"))["request_id"] == "abc123"
    finally:
        request_id_var.reset(token)


def test_sem_request_id_a_chave_nao_aparece():
    """Log de startup não tem requisição — melhor omitir que emitir null."""
    assert "request_id" not in _formata(_record("iniciando"))


async def test_resposta_traz_o_header(client):
    resp = await client.get("/api/v1/health")

    assert resp.headers.get(HEADER_REQUEST_ID)
    assert len(resp.headers[HEADER_REQUEST_ID]) >= 16


async def test_request_id_do_proxy_e_respeitado(client):
    """Se o proxy já gerou um id, o rastro precisa atravessar as camadas."""
    resp = await client.get("/api/v1/health", headers={HEADER_REQUEST_ID: "id-vindo-do-proxy"})

    assert resp.headers[HEADER_REQUEST_ID] == "id-vindo-do-proxy"


async def test_cada_requisicao_tem_id_proprio(client):
    a = await client.get("/api/v1/health")
    b = await client.get("/api/v1/health")

    assert a.headers[HEADER_REQUEST_ID] != b.headers[HEADER_REQUEST_ID]


async def test_id_nao_vaza_entre_requisicoes(client):
    """O ContextVar precisa ser resetado — senão o id de uma requisição gruda na seguinte."""
    await client.get("/api/v1/health")
    assert request_id_var.get() is None


# ── Configuração ─────────────────────────────────────────────────────────

def test_setup_logging_em_producao_usa_json(caplog):
    setup_logging(level="INFO", json_output=True)
    raiz = logging.getLogger()

    assert isinstance(raiz.handlers[0].formatter, JsonFormatter)

    # Restaura formato legível para não poluir a saída dos demais testes.
    setup_logging(level="WARNING", json_output=False)


def test_setup_logging_em_dev_usa_formato_legivel():
    setup_logging(level="INFO", json_output=False)
    raiz = logging.getLogger()

    assert not isinstance(raiz.handlers[0].formatter, JsonFormatter)
    setup_logging(level="WARNING", json_output=False)


# ── SQL não pode vazar para o log ────────────────────────────────────────

def test_sqlalchemy_nao_loga_statements():
    """
    Com o root em INFO, o SQLAlchemy registra cada statement COM PARÂMETROS —
    o que colocaria `prompt_text` e e-mail no log de produção. O DLP protege a
    saída para os provedores; não adianta vazar pelo log.
    """
    setup_logging(level="INFO", json_output=True)

    for nome in ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool"):
        assert not logging.getLogger(nome).isEnabledFor(logging.INFO), (
            f"{nome} está habilitado para INFO — statements SQL com parâmetros vão para o log"
        )

    setup_logging(level="WARNING", json_output=False)


def test_httpx_nao_loga_urls():
    """A URL completa pode carregar e-mail em query string."""
    setup_logging(level="INFO", json_output=True)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    setup_logging(level="WARNING", json_output=False)


def test_o_log_da_aplicacao_continua_em_info():
    """Contraprova: silenciar biblioteca não pode silenciar a aplicação."""
    setup_logging(level="INFO", json_output=True)
    assert logging.getLogger("app.services.orquestrador_service").isEnabledFor(logging.INFO)
    setup_logging(level="WARNING", json_output=False)
