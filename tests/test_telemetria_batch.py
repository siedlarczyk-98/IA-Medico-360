"""
O Phoenix exporta spans em LOTE, fora do event loop.

`register()` sem `batch=True` instala o SimpleSpanProcessor, que exporta cada
span de forma síncrona dentro do `on_end`, com cliente HTTP bloqueante. A API
roda num único event loop: cada resposta congelava todas as outras por um round
trip, e um Phoenix lento congelava tudo. Confirmado ativo em produção em
2026-09-21 (`PHOENIX_API_KEY` definida).

O teste espiona a chamada em vez de inspecionar o provider: o que importa é o
argumento que a aplicação passa, e montar um provider real tentaria sair para
a rede.
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
