"""
Médico 360 — Observabilidade com Arize Phoenix (OpenTelemetry).

O projeto chama os providers via httpx diretamente (sem SDKs oficiais),
então os auto-instrumentors do OpenInference não funcionam aqui.
Em vez disso, emitimos spans manuais seguindo o schema OpenInference:
https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
"""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_tracer: trace.Tracer | None = None


def setup_phoenix(api_key: str, project_name: str, endpoint: str) -> None:
    """Inicializa o tracer Phoenix. Chame uma vez no startup da aplicação."""
    global _tracer

    if not api_key:
        logger.info("PHOENIX_API_KEY não configurada — observabilidade desativada.")
        return

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource(attributes={"service.name": project_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"api_key": api_key},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("medico360.ai_providers")
        logger.info("Phoenix telemetry ativada → projeto '%s'", project_name)
    except ImportError:
        logger.warning(
            "Pacotes de telemetria não instalados. "
            "Execute: pip install arize-phoenix-otel opentelemetry-exporter-otlp-proto-http"
        )


def get_tracer() -> trace.Tracer | None:
    return _tracer


# ── Helpers de span ──────────────────────────────────────────

def _set_llm_attributes(span: trace.Span, provider: str, model_id: str, prompt: str) -> None:
    span.set_attribute("openinference.span.kind", "LLM")
    span.set_attribute("llm.provider", provider)
    span.set_attribute("llm.model_name", model_id)
    span.set_attribute("input.value", prompt[:2000])  # trunca para evitar payloads gigantes


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


@contextmanager
def llm_span(provider: str, model_id: str, prompt: str, operation: str = "complete") -> Iterator[trace.Span]:
    """Context manager para spans de chamadas LLM síncronas/completas."""
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


@asynccontextmanager
async def async_llm_span(provider: str, model_id: str, prompt: str, operation: str = "complete") -> AsyncIterator[trace.Span]:
    """Context manager para spans de chamadas LLM assíncronas."""
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
