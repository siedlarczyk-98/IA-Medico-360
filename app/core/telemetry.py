"""
Médico 360 — Observabilidade com Arize Phoenix (OpenTelemetry).

O projeto chama os providers via httpx diretamente (sem SDKs oficiais),
então os auto-instrumentors do OpenInference não funcionam aqui.
Em vez disso, emitimos spans manuais seguindo o schema OpenInference:
https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import wraps

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
        import logging as _logging
        import os

        from phoenix.otel import register

        # Loga erros de export do SDK OTel (normalmente silenciosos)
        _logging.getLogger("opentelemetry.exporter.otlp").setLevel(_logging.DEBUG)
        _logging.getLogger("opentelemetry.sdk.trace.export").setLevel(_logging.DEBUG)

        os.environ.setdefault("PHOENIX_API_KEY", api_key.strip())
        os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", endpoint.strip())

        tracer_provider = register(project_name=project_name)
        _tracer = tracer_provider.get_tracer("medico360.ai_providers")
        logger.info("Phoenix ativado → projeto='%s' endpoint='%s' tracer=%s", project_name, endpoint, _tracer)
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


def get_current_span() -> trace.Span | None:
    """
    O span da interação em curso, ou None se o Phoenix estiver desligado.

    Serve para carimbar atributos LONGE de onde o span foi aberto — o custo é
    calculado ~150 linhas depois do início do `query`, e passá-lo de mão em mão
    por toda a função só para chegar lá acrescentaria um parâmetro a cada
    assinatura no caminho.

    Devolve None quando não há span gravando, e não o span "inválido" que o
    OTel usa como sentinela: quem chama trata os dois do mesmo jeito, e None é
    mais honesto sobre o que aconteceu.
    """
    if _tracer is None:
        return None
    span = trace.get_current_span()
    return span if span.is_recording() else None


@asynccontextmanager
async def interaction_span(mode: str | None, operation: str = "orquestrador") -> AsyncIterator[trace.Span | None]:
    """
    Span que cobre a interação INTEIRA, do roteamento ao custo gravado.

    Existe por uma razão de ordem: o span do provider (`async_llm_span`) fecha
    quando a chamada HTTP retorna, e o custo só é calculado DEPOIS disso — ele
    precisa da tabela de preços do banco. Não havia onde carimbar o custo: o
    único span disponível já estava fechado.

    Este é o pai. Os spans de provider ficam aninhados dentro dele (o OTel usa
    o contexto atual como pai automaticamente), e ele continua aberto tempo
    suficiente para receber o total via `set_llm_cost`.

    Devolve None quando o Phoenix está desligado, e quem chama passa esse None
    adiante sem se importar — `set_llm_cost` aceita.
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(f"medico360.{operation}") as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        if mode:
            span.set_attribute("medico360.mode", mode)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.StatusCode.ERROR, str(exc))
            raise


def traced_interaction(operation: str = "orquestrador"):
    """
    Decorator que abre o span-pai em volta de um método do orquestrador.

    Decorator, e não um `async with` dentro do método, por um motivo prático: o
    corpo do `query` tem ~300 linhas e o do `stream` é um gerador. Envolver
    qualquer um dos dois exigiria reindentar tudo, e o diff resultante — 300
    linhas de espaço em branco — esconderia a mudança real de quem for revisar.

    O `mode` vem dos kwargs quando o cliente o informou explicitamente. Ele
    ainda pode MUDAR lá dentro (a triagem decide, ou o anexo promove), e por
    isso `set_llm_cost` o carimba de novo com o valor final — o daqui é só o
    que se sabia no começo.
    """
    def decorador(fn):
        @wraps(fn)
        async def wrapper(self, *args, **kwargs):
            async with interaction_span(kwargs.get("mode"), operation):
                return await fn(self, *args, **kwargs)
        return wrapper
    return decorador


def traced_interaction_stream(operation: str = "orquestrador.stream"):
    """
    Versão do `traced_interaction` para geradores assíncronos.

    Um `async def` que dá `yield` não pode ser envolvido pelo decorator acima:
    chamá-lo devolve o gerador na hora, sem executar nada, e o span fecharia
    antes do primeiro token. Aqui o `async for` mantém o span aberto pelo tempo
    de vida do stream inteiro — que é justamente o que o `/stream` precisa,
    porque lá o custo só é calculado quando a geração termina.
    """
    def decorador(fn):
        @wraps(fn)
        async def wrapper(self, *args, **kwargs):
            async with interaction_span(kwargs.get("mode"), operation):
                async for item in fn(self, *args, **kwargs):
                    yield item
        return wrapper
    return decorador


def set_llm_cost(
    span: trace.Span | None,
    *,
    cost_usd: object,
    tool_usage: dict | None = None,
    mode: str | None = None,
) -> None:
    """
    Carimba no span o custo REAL da interação, já calculado pelo orquestrador.

    Por que isto não sai de `_set_llm_output`: quando o provider retorna, o
    custo ainda não existe. Ele depende da tabela de preços (`model_pricing`,
    no banco) e, no caso das ferramentas integradas, de uma conversão de reais
    para dólar — nada disso é assunto do provider, que só sabe falar HTTP com a
    API. Quem tem os dois números é o orquestrador, depois do `calculate_cost`.

    Por que importa: sem este atributo o Phoenix ESTIMA o custo a partir do
    modelo e da contagem de tokens. Para a maioria dos modos a estimativa é
    aproximada e serve. Para o DATA_OCEAN ela é simplesmente errada — o custo
    dele está em GB processados, páginas lidas e minutos de execução, não em
    tokens. Uma consulta agêntica de dezenas de segundos ao DATASUS aparecia no
    Phoenix custando o mesmo que uma pergunta comum ao mesmo modelo.

    `tool_usage` vai junto, cru, pelo mesmo motivo que ele é gravado cru em
    `extra_metadata`: os preços da Maritaca mudam, e o consumo permite refazer
    a conta depois. Sem ele, o span registraria um total sem nada que explique
    de onde veio.

    Silencioso quando o span é None ou não está gravando — Phoenix desligado é
    o caminho normal em teste e em desenvolvimento.
    """
    if span is None or not span.is_recording():
        return

    # `float` porque o custo circula como `Decimal` (dinheiro), e o OTel só
    # aceita tipos primitivos como valor de atributo. A precisão perdida aqui
    # não tem consequência: o valor autoritativo é o do banco, e este é para
    # leitura humana num gráfico.
    span.set_attribute("llm.cost.total", float(cost_usd))

    if mode:
        span.set_attribute("medico360.mode", mode)

    # Consumo bruto por unidade, do jeito que a Maritaca reporta. Prefixo
    # próprio: não é convenção OpenInference, e inventar um nome parecido com
    # os dela confundiria quem lê o trace.
    for unidade, consumo in (tool_usage or {}).items():
        if consumo:
            span.set_attribute(f"medico360.tool_usage.{unidade}", consumo)


def start_llm_span(provider: str, model_id: str, prompt: str, operation: str = "stream") -> trace.Span | None:
    """Abre um span manualmente — use em geradores onde context manager não cabe.
    Chame span.end() quando o stream terminar."""
    tracer = get_tracer()
    if tracer is None:
        logger.debug("start_llm_span: tracer é None — Phoenix não inicializado")
        return None
    span = tracer.start_span(f"{provider}.{operation}")
    logger.debug("span criado: %s.%s recording=%s", provider, operation, span.is_recording())
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
