"""
Médico 360 — Log estruturado com correlação por requisição.

O log era texto livre: investigar um incidente significava ler linha a linha,
sem conseguir ligar o erro à requisição que o causou. Agora cada linha sai em
JSON com um `request_id` que também vai para o Sentry e para o header de
resposta — dado um erro, dá para reconstruir a requisição inteira.

O que NUNCA entra no log: conteúdo de prompt, texto extraído de arquivo, e-mail.
Correlação se faz por id, não por dado de paciente (ver `app/core/error_tracking.py`).
"""

import json
import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

# ContextVar e não parâmetro: o id precisa alcançar qualquer `logger.x()` no
# meio da pilha sem ser passado de mão em mão por toda função.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

HEADER_REQUEST_ID = "X-Request-ID"

# Atributos internos do LogRecord — tudo que não estiver aqui é campo extra
# posto pelo chamador e vai para o JSON.
_ATRIBUTOS_PADRAO = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "asctime", "message", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Formata o registro como uma linha JSON."""

    def format(self, record: logging.LogRecord) -> str:
        saida = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        rid = request_id_var.get()
        if rid:
            saida["request_id"] = rid

        if record.exc_info:
            saida["exception"] = self.formatException(record.exc_info)

        for chave, valor in record.__dict__.items():
            if chave not in _ATRIBUTOS_PADRAO and not chave.startswith("_"):
                saida[chave] = valor

        return json.dumps(saida, ensure_ascii=False, default=str)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Atribui um id a cada requisição e devolve no header.

    Respeita um `X-Request-ID` que já venha do proxy, para o rastro atravessar
    as camadas em vez de recomeçar aqui.
    """

    async def dispatch(self, request, call_next):
        rid = request.headers.get(HEADER_REQUEST_ID) or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            # Marca também no Sentry: o evento de erro passa a carregar o mesmo
            # id que aparece no log e no trace do Phoenix.
            try:
                import sentry_sdk

                sentry_sdk.set_tag("request_id", rid)
            except Exception:
                pass

            resposta = await call_next(request)
            resposta.headers[HEADER_REQUEST_ID] = rid
            return resposta
        finally:
            request_id_var.reset(token)


def setup_logging(level: str = "INFO", json_output: bool = True) -> None:
    """
    Configura o logging raiz.

    `json_output=False` mantém o formato legível para desenvolvimento local —
    JSON é ótimo para agregador de log e péssimo para ler no terminal.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s")
    )

    raiz = logging.getLogger()
    raiz.handlers.clear()
    raiz.addHandler(handler)
    raiz.setLevel(level.upper())

    # O uvicorn instala handlers próprios; sem isso cada linha sai duplicada,
    # uma em JSON e outra no formato dele.
    for nome in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        log_uvicorn = logging.getLogger(nome)
        log_uvicorn.handlers.clear()
        log_uvicorn.propagate = True

    _silencia_bibliotecas_ruidosas()


# Bibliotecas que, no nível INFO, emitem dado sensível ou volume inútil.
# O caso do SQLAlchemy é de segurança, não de ruído: com o root em INFO ele
# passa a registrar CADA statement COM OS PARÂMETROS — ou seja, `prompt_text`,
# e-mail e tudo mais que trafega numa query iria para o log de produção. O DLP
# protege a saída para os provedores de IA; não adianta vazar pelo log.
_BIBLIOTECAS_SILENCIADAS = {
    "sqlalchemy.engine": logging.WARNING,
    "sqlalchemy.engine.Engine": logging.WARNING,
    "sqlalchemy.pool": logging.WARNING,
    "sqlalchemy.dialects": logging.WARNING,
    "sqlalchemy.orm": logging.WARNING,
    # httpx registra a URL completa de cada requisição, e query string pode
    # carregar e-mail (ex.: a validação de membro da Curseduca).
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "asyncio": logging.WARNING,
}


def _silencia_bibliotecas_ruidosas() -> None:
    for nome, nivel in _BIBLIOTECAS_SILENCIADAS.items():
        logging.getLogger(nome).setLevel(nivel)
