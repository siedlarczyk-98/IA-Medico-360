"""
Médico 360 — Observabilidade com Arize Phoenix (OpenTelemetry).

O projeto chama os providers via httpx diretamente (sem SDKs oficiais),
então os auto-instrumentors do OpenInference não funcionam aqui.
Em vez disso, emitimos spans manuais seguindo o schema OpenInference:
https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from opentelemetry import trace

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None


def setup_phoenix(api_key: str, project_name: str, endpoint: str) -> None:
    """Inicializa o tracer Phoenix via arize-phoenix-otel. Chame uma vez no startup."""
    global _tracer

    if not api_key:
        logger.info("PHOENIX_API_KEY não configurada — observabilidade desativada.")
        return

    try:
        import os
        from phoenix.otel import register

        os.environ.setdefault("PHOENIX_API_KEY", api_key)
        os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", endpoint)

        tracer_provider = register(project_name=project_name)
        _tracer = tracer_provider.get_tracer("medico360.ai_providers")
        logger.info("Phoenix telemetry ativada → projeto '%s' / endpoint '%s'", project_name, endpoint)
    except ImportError:
        logger.warning("arize-phoenix-otel não instalado. Execute: pip install arize-phoenix-otel")
    except Exception as exc:
        logger.warning("Falha ao inicializar Phoenix: %s", exc)


def get_tracer() -> trace.Tracer | None:
    return _tracer


# ── Helpers de span ──────────────────────────────────────────

def _set_llm_attributes(span: trace.Span, provider: str, model_id: str, prompt: str) -> None:
    span.set_attribute("openinference.span.kind", "LLM")
    span.set_attribute("llm.provider", provider)
    span.set_attribute("llm.model_name", model_id)
    span.set_attribute("input.value", prompt[:2000])


def _set_llm_output(
    span: trace.Span,
    text: str,
    tokens_in: int | None,
    tokens_out: int | None,
) -> None:
    span.set_attribute("output.value", text[:2000])
    if tokens_in is not None:
        span.set_attribute("llm.token_count.prompt", tokens_in)
    if tokens_out is not None:
        span.set_attribute("llm.token_count.completion", tokens_out)
    if tokens_in and tokens_out:
        span.set_attribute("llm.token_count.total", tokens_in + tokens_out)


def start_llm_span(provider: str, model_id: str, prompt: str, operation: str = "stream") -> trace.Span | None:
    """Abre um span manualmente — use em geradores onde context manager não cabe.
    Chame span.end() quando o stream terminar."""
    tracer = get_tracer()
    if tracer is None:
        return None
    span = tracer.start_span(f"{provider}.{operation}")
    _set_llm_attributes(span, provider, model_id, prompt)
    return span


@asynccontextmanager
async def async_llm_span(provider: str, model_id: str, prompt: str, operation: str = "complete") -> AsyncIterator[trace.Span]:
    tracer = get_tracer()
    if tracer is None:
        yield trace.NonRecordingSpan(trace.INVALID_SPAN_CONTEXT)
        return

    with tracer.start_as_current_span(f"{provider}.{operation}") as span:
        _set_llm_attributes(span, provider, model_id, prompt)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise
