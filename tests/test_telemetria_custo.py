"""
Custo real no trace do Phoenix.

O Phoenix ESTIMA custo a partir do modelo e da contagem de tokens quando o
span não traz o valor. Para a maioria dos modos isso é aproximado e serve;
para o DATA_OCEAN é errado, porque o custo dele está em GB processados,
páginas lidas e minutos de execução — não em tokens. Uma consulta agêntica de
dezenas de segundos ao DATASUS aparecia custando o mesmo que uma pergunta
comum ao mesmo modelo.

O que este arquivo protege: que o custo JÁ CALCULADO pelo orquestrador chegue
ao span, junto do consumo bruto que o explica.

Os spans são fabricados aqui em vez de subir um coletor: o alvo do teste são
os ATRIBUTOS que emitimos, não o transporte OTel.
"""

from decimal import Decimal

import pytest

from app.core import telemetry


class SpanFalso:
    """Span que só guarda o que foi carimbado nele."""

    def __init__(self, recording: bool = True):
        self.atributos: dict = {}
        self.excecoes: list = []
        self.status = None
        self._recording = recording

    def is_recording(self) -> bool:
        return self._recording

    def set_attribute(self, chave, valor) -> None:
        self.atributos[chave] = valor

    # O span real do OTel expõe os dois métodos abaixo, e `interaction_span` os
    # chama quando o corpo estoura. Sem eles aqui, o dublê falharia por não ser
    # um span — escondendo o que o teste quer medir.
    def record_exception(self, exc) -> None:
        self.excecoes.append(exc)

    def set_status(self, *args) -> None:
        self.status = args


# ── O custo chega ao span ────────────────────────────────────────────────────

def test_custo_vai_para_o_span():
    span = SpanFalso()
    telemetry.set_llm_cost(span, cost_usd=Decimal("0.0342"), mode="DATA_OCEAN")

    assert span.atributos["llm.cost.total"] == pytest.approx(0.0342)
    assert span.atributos["medico360.mode"] == "DATA_OCEAN"


def test_decimal_vira_float_porque_otel_nao_aceita_decimal():
    """
    O custo circula como `Decimal` (é dinheiro), mas o OTel só aceita
    primitivos. Um `Decimal` cru no atributo é descartado pelo SDK em silêncio
    — o pior modo de falhar, porque o trace continua saindo, só que sem custo.
    """
    span = SpanFalso()
    telemetry.set_llm_cost(span, cost_usd=Decimal("0.123456"))

    assert isinstance(span.atributos["llm.cost.total"], float)


def test_consumo_bruto_das_ferramentas_acompanha_o_custo():
    """
    O total sozinho não se explica. O consumo cru vai junto pelo mesmo motivo
    que é gravado em `extra_metadata`: os preços da Maritaca mudam, e sem o
    consumo não há como refazer a conta depois.
    """
    span = SpanFalso()
    telemetry.set_llm_cost(
        span,
        cost_usd=Decimal("0.05"),
        tool_usage={"data_ocean_gb_processed": 2.5, "page_reads": 12},
        mode="DATA_OCEAN",
    )

    assert span.atributos["medico360.tool_usage.data_ocean_gb_processed"] == 2.5
    assert span.atributos["medico360.tool_usage.page_reads"] == 12


def test_unidade_zerada_nao_polui_o_trace():
    """A API reporta as quatro unidades sempre; só as usadas interessam."""
    span = SpanFalso()
    telemetry.set_llm_cost(
        span,
        cost_usd=Decimal("0.01"),
        tool_usage={"data_ocean_gb_processed": 1.0, "code_execution_minutes": 0},
    )

    assert "medico360.tool_usage.data_ocean_gb_processed" in span.atributos
    assert "medico360.tool_usage.code_execution_minutes" not in span.atributos


# ── Phoenix desligado é o caminho normal ─────────────────────────────────────

def test_span_none_nao_quebra():
    """
    Phoenix desligado é o normal em teste e em desenvolvimento — e o custo é
    calculado do mesmo jeito. Isto não pode virar um `AttributeError` no meio
    da resposta ao médico.
    """
    telemetry.set_llm_cost(None, cost_usd=Decimal("0.01"), mode="DATA_OCEAN")


def test_span_que_nao_grava_e_ignorado():
    span = SpanFalso(recording=False)
    telemetry.set_llm_cost(span, cost_usd=Decimal("0.01"))

    assert span.atributos == {}


def test_sem_tracer_nao_ha_span_corrente(monkeypatch):
    """`get_current_span` devolve None com o Phoenix desligado, não o span
    sentinela do OTel — quem chama trata os dois igual, e None é mais honesto."""
    monkeypatch.setattr(telemetry, "_tracer", None)

    assert telemetry.get_current_span() is None


# ── O span-pai sobrevive ao stream ───────────────────────────────────────────

async def test_span_do_stream_fica_aberto_ate_o_ultimo_token():
    """
    O decorator do `/stream` envolve um GERADOR, e é aí que mora o risco: um
    decorator comum devolveria o gerador sem executar nada e o span fecharia
    antes do primeiro token — justamente quando o custo ainda não foi
    calculado. `traced_interaction_stream` mantém o span aberto pelo `async
    for` até o gerador se esgotar.

    O teste registra o ESTADO DO SPAN a cada yield. Verificar só que os itens
    chegaram não prova nada: um decorator que fecha o span antes de iterar
    entrega os mesmos itens. É o `fechado_em` que distingue os dois.
    """
    from contextlib import contextmanager

    estado_por_yield: list[bool] = []

    class SpanRastreado(SpanFalso):
        def __init__(self):
            super().__init__()
            self.fechado = False

    span = SpanRastreado()

    class TracerFalso:
        def start_as_current_span(self, nome):
            @contextmanager
            def _cm():
                try:
                    yield span
                finally:
                    span.fechado = True
            return _cm()

    class ServicoFalso:
        @telemetry.traced_interaction_stream()
        async def stream(self, *, mode=None):
            for i in range(3):
                estado_por_yield.append(span.fechado)
                yield i

    telemetry._tracer = TracerFalso()
    try:
        recebidos = [x async for x in ServicoFalso().stream(mode="DATA_OCEAN")]
    finally:
        telemetry._tracer = None

    assert recebidos == [0, 1, 2]
    assert estado_por_yield == [False, False, False], (
        "o span fechou antes do stream terminar — o custo é calculado DEPOIS "
        "do último token e não teria onde ser carimbado"
    )
    assert span.fechado, "o span precisa fechar quando o gerador se esgota"
    assert span.atributos["medico360.mode"] == "DATA_OCEAN"


async def test_span_do_stream_fecha_mesmo_com_erro_no_meio():
    """Um stream que estoura no meio não pode deixar o span pendurado."""
    from contextlib import contextmanager

    span = SpanFalso()
    fechou: list[bool] = []

    class TracerFalso:
        def start_as_current_span(self, nome):
            @contextmanager
            def _cm():
                try:
                    yield span
                finally:
                    fechou.append(True)
            return _cm()

    class ServicoFalso:
        @telemetry.traced_interaction_stream()
        async def stream(self, *, mode=None):
            yield 1
            raise RuntimeError("provider caiu")

    telemetry._tracer = TracerFalso()
    try:
        with pytest.raises(RuntimeError, match="provider caiu"):
            [x async for x in ServicoFalso().stream(mode="DATA_OCEAN")]
    finally:
        telemetry._tracer = None

    assert fechou == [True]
