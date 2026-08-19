"""
Médico 360 — Rastreamento de erro (Sentry).

RN-SEC-001 vale aqui também: um Sentry na configuração padrão captura corpo de
requisição, cookies e AS VARIÁVEIS LOCAIS de cada frame do stack trace. Nesta
aplicação isso significa o prompt clínico bruto — antes do DLP — sendo enviado
para fora do país num evento de erro. A ferramenta de observabilidade viraria
exatamente o vazamento que o DLP existe para impedir.

Por isso o `before_send` abaixo é obrigatório e testado (`tests/test_error_tracking.py`),
não uma precaução opcional. A regra é lista de bloqueio por NOME de campo, não
inspeção de conteúdo: é mais previsível e não depende de acertar um regex.

No-op quando `sentry_dsn` está vazio — igual ao Phoenix.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Campos que podem carregar conteúdo clínico, PII ou credencial. Comparação é
# por substring no nome, em minúsculas — "user_prompt" e "promptText" batem.
CAMPOS_BLOQUEADOS = frozenset({
    "prompt", "text", "content", "message", "messages", "answer", "resposta",
    "extracted_text", "response_text", "description", "descricao",
    "body", "payload", "inputs", "query",
    "email", "cpf", "phone", "telefone", "name", "nome", "crm",
    "password", "senha", "token", "secret", "api_key", "apikey",
    "authorization", "cookie", "session",
    "image_base64", "base64", "file", "arquivo",
})

MASCARA = "[REMOVIDO PELO SCRUBBING]"

_MAX_PROFUNDIDADE = 8


def _bloqueado(chave: str) -> bool:
    k = str(chave).lower()
    return any(proibido in k for proibido in CAMPOS_BLOQUEADOS)


def _limpa(valor: Any, profundidade: int = 0) -> Any:
    """Percorre a estrutura e mascara todo valor sob chave bloqueada."""
    if profundidade > _MAX_PROFUNDIDADE:
        return MASCARA
    if isinstance(valor, dict):
        return {
            chave: MASCARA if _bloqueado(chave) else _limpa(v, profundidade + 1)
            for chave, v in valor.items()
        }
    if isinstance(valor, list | tuple):
        return [_limpa(v, profundidade + 1) for v in valor]
    return valor


def scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    """
    `before_send` do Sentry. Remove tudo que possa carregar dado de paciente.

    Falha fechada: se o scrubbing der erro, o evento é DESCARTADO em vez de
    enviado sem limpeza — perder um alerta é melhor que vazar prontuário.
    """
    try:
        # 1. Corpo da requisição: nunca é necessário para diagnosticar, e é
        #    justamente onde o prompt chega.
        requisicao = event.get("request")
        if isinstance(requisicao, dict):
            requisicao.pop("data", None)
            requisicao.pop("cookies", None)
            cabecalhos = requisicao.get("headers")
            if isinstance(cabecalhos, dict):
                requisicao["headers"] = {
                    k: (MASCARA if _bloqueado(k) else v) for k, v in cabecalhos.items()
                }
            # A query string pode carregar e-mail (ex.: ?email=...).
            requisicao.pop("query_string", None)

        # 2. Variáveis locais dos frames — o vazamento menos óbvio e o mais grave.
        for excecao in (event.get("exception") or {}).get("values", []) or []:
            for frame in (excecao.get("stacktrace") or {}).get("frames", []) or []:
                if isinstance(frame.get("vars"), dict):
                    frame["vars"] = _limpa(frame["vars"])

        # 3. Idem para threads (stack trace sem exceção).
        for thread in (event.get("threads") or {}).get("values", []) or []:
            for frame in (thread.get("stacktrace") or {}).get("frames", []) or []:
                if isinstance(frame.get("vars"), dict):
                    frame["vars"] = _limpa(frame["vars"])

        # 4. Contexto adicional e migalhas de navegação.
        for secao in ("extra", "contexts", "tags"):
            if isinstance(event.get(secao), dict):
                event[secao] = _limpa(event[secao])

        migalhas = event.get("breadcrumbs")
        if isinstance(migalhas, dict) and isinstance(migalhas.get("values"), list):
            migalhas["values"] = _limpa(migalhas["values"])

        # 5. Identificação: id do usuário serve para correlacionar; e-mail não.
        usuario = event.get("user")
        if isinstance(usuario, dict):
            event["user"] = {"id": usuario.get("id")} if usuario.get("id") else {}

        return event
    except Exception as e:
        logger.error("Scrubbing do Sentry falhou; evento descartado. %s", e)
        return None


def setup_sentry(dsn: str, environment: str, release: str | None = None) -> bool:
    """Inicializa o Sentry. Retorna False (no-op) se não houver DSN configurado."""
    if not dsn:
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            # Nunca ligar: é o que manda cookies, headers e corpo por padrão.
            send_default_pii=False,
            before_send=scrub_event,
            before_send_transaction=scrub_event,
            # Amostragem de performance desligada por ora — o objetivo aqui é
            # alerta de erro, e trace de LLM já vive no Phoenix.
            traces_sample_rate=0.0,
        )
        return True
    except Exception as e:
        logger.error("Sentry não inicializado: %s", e)
        return False
