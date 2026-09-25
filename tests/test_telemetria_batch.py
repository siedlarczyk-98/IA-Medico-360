"""
O Phoenix exporta spans em LOTE, fora do event loop.

`register()` sem `batch=True` instala o SimpleSpanProcessor, que exporta cada
span de forma síncrona dentro do `on_end`, com cliente HTTP bloqueante. A API
roda num único event loop: cada resposta congelava todas as outras por um round
trip, e um Phoenix lento congelava tudo. Confirmado ativo em produção em
2026-09-21 (`PHOENIX_API_KEY` definida).

Os testes de argumento espionam a chamada: o que importa ali é o que a aplicação
passa. O último usa o `register()` de verdade, porque o que ele guarda é a
compatibilidade entre as versões instaladas — montar o provider não sai para a
rede enquanto nenhum span é criado.
"""

import sys
import types

from app.core import telemetry


class _ProviderFalso:
    def get_tracer(self, _nome):
        return object()


def _instala_register_espiao(monkeypatch) -> list[dict]:
    chamadas: list[dict] = []

    def register(**kwargs):
        chamadas.append(kwargs)
        return _ProviderFalso()

    modulo = types.ModuleType("phoenix.otel")
    modulo.register = register
    monkeypatch.setitem(sys.modules, "phoenix.otel", modulo)
    # `setup_phoenix` faz `os.environ.setdefault` das duas variáveis. Definidas
    # pelo monkeypatch, o setdefault vira no-op e o valor some no fim do teste,
    # em vez de vazar para o resto da suíte.
    monkeypatch.setenv("PHOENIX_API_KEY", "chave-de-teste")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://phoenix.invalid")
    return chamadas


def test_register_e_chamado_com_batch(monkeypatch):
    chamadas = _instala_register_espiao(monkeypatch)
    monkeypatch.setattr(telemetry, "_tracer", None)

    telemetry.setup_phoenix("chave-de-teste", "projeto-teste", "https://phoenix.invalid")

    assert len(chamadas) == 1
    assert chamadas[0].get("batch") is True, (
        "register() precisa receber batch=True — sem isso cada span é exportado "
        "de forma síncrona no event loop e congela as demais respostas."
    )


def test_sem_chave_nao_registra_nada(monkeypatch):
    chamadas = _instala_register_espiao(monkeypatch)
    monkeypatch.setattr(telemetry, "_tracer", None)

    telemetry.setup_phoenix("", "projeto-teste", "https://phoenix.invalid")

    assert chamadas == []
    assert telemetry.get_tracer() is None


def test_falha_no_register_alarma_e_nao_derruba_o_boot(monkeypatch):
    """Em 25/09/2026 o Phoenix foi achado desligado em produção: o `register()`
    levantava AttributeError (OpenTelemetry 1.45 incompatível), o erro virava uma
    linha de aviso no meio do boot, e a API subia sem telemetria sem ninguém saber."""
    _instala_register_espiao(monkeypatch)

    def register_quebrado(**_kwargs):
        raise AttributeError("'HTTPSpanExporter' object has no attribute '_headers'")

    sys.modules["phoenix.otel"].register = register_quebrado
    monkeypatch.setattr(telemetry, "_tracer", None)

    alarmes: list[dict] = []
    from app.core import alarme

    monkeypatch.setattr(alarme, "alarmar", lambda **kw: alarmes.append(kw) or True)

    telemetry.setup_phoenix("chave-de-teste", "projeto-teste", "https://phoenix.invalid")

    assert telemetry.get_tracer() is None
    assert [a["tag"] for a in alarmes] == ["phoenix_desligado"]
    assert "_headers" in alarmes[0]["contexto"]["erro"]


def test_o_register_real_funciona_com_as_versoes_instaladas(monkeypatch):
    """Sem espião: o `register()` do phoenix-otel contra o OpenTelemetry que o
    `requirements.txt` instala. É este teste que pega, no CI e antes do deploy,
    uma versão do OpenTelemetry que o phoenix-otel não suporta — foi o que
    desligou o Phoenix em produção em 25/09/2026.

    Não sai para a rede: montar o exportador não conecta, e nenhum span é criado.

    Duas condições, medidas: sem elas o teste passa com a versão quebrada.
    - SEM `verbose=False`: o atributo que sumiu na 1.45 só é lido quando o
      `register()` imprime o banner de configuração — o padrão, e é como
      `setup_phoenix` chama.
    - Endpoint COM CAMINHO, no formato do Arize (`.../s/<espaço>`): é o que cai no
      exportador HTTP. Um host sem caminho escolhe outro exportador e não quebra.
    """
    from phoenix.otel import register

    monkeypatch.setenv("PHOENIX_API_KEY", "chave-de-teste")
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "https://phoenix.invalid/s/espaco-de-teste")

    provider = register(
        project_name="projeto-teste",
        batch=True,
        set_global_tracer_provider=False,
    )
    try:
        assert provider.get_tracer("teste") is not None
    finally:
        provider.shutdown()
