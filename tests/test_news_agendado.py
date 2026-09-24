"""
O agendador de notícias não pula horas (item 62 de `docs/pitacos-do-fable-2.md`).

Ele dormia 3600 s DEPOIS de cada rodada, e o relógio andava junto com a duração
do pipeline: uma rodada às 10:59:30 que levasse 90 s acordava às 12:01, e a hora
11 nunca era vista. A coleta roda numa hora só (`news_run_hour`) e cada faixa do
digest também — a hora pulada perdia o dia inteiro, e a idempotência por data
não recuperava nada, porque nada chegava a rodar.
"""

from datetime import UTC, datetime

import pytest

from app.services import news_agendado
from app.services.news_agendado import (
    FOLGA_APOS_VIRADA_SEGUNDOS,
    MAX_HORAS_RECUPERADAS,
    horas_a_processar,
    processar_pendentes,
    segundos_ate_proxima_hora,
)


def h(hora: int, minuto: int = 0, segundo: int = 0) -> datetime:
    return datetime(2026, 9, 24, hora, minuto, segundo, tzinfo=UTC)


def test_dorme_ate_a_virada_da_hora_e_nao_uma_hora_inteira():
    # O cenário do relatório: a rodada terminou às 11:01. Com o sono fixo de
    # 3600 s, o próximo despertar seria 12:01 — e a hora 11 já teria passado.
    assert segundos_ate_proxima_hora(h(10, 59, 30)) == 30 + FOLGA_APOS_VIRADA_SEGUNDOS
    assert segundos_ate_proxima_hora(h(11, 1)) == 59 * 60 + FOLGA_APOS_VIRADA_SEGUNDOS


def test_primeira_rodada_serve_so_a_hora_atual():
    assert horas_a_processar(None, h(11, 2)) == [h(11)]


def test_hora_ja_servida_nao_roda_de_novo():
    # Acordar duas vezes na mesma hora (folga, relógio) não pode dobrar o envio.
    assert horas_a_processar(h(11), h(11, 40)) == []


def test_hora_pulada_e_recuperada_em_ordem():
    assert horas_a_processar(h(10), h(12, 1)) == [h(11), h(12)]


def test_recuperacao_tem_limite():
    """Um resumo da manhã entregue à noite já não é o que o médico pediu."""
    horas = horas_a_processar(h(1), h(12, 1))
    assert len(horas) == MAX_HORAS_RECUPERADAS
    assert horas[-1] == h(12)


@pytest.fixture
def rodadas(monkeypatch):
    """Troca a rodada real (banco, NCBI, e-mail) por um registro das horas pedidas."""
    pedidas: list[datetime] = []
    falhar_em: set[datetime] = set()

    async def _rodada(hora):
        pedidas.append(hora)
        if hora in falhar_em:
            raise RuntimeError("NCBI fora do ar")

    monkeypatch.setattr(news_agendado, "_uma_rodada", _rodada)
    return pedidas, falhar_em


async def test_o_cenario_do_relatorio_nao_perde_a_hora_11(rodadas):
    pedidas, _ = rodadas

    # 10:59:30 — a rodada das 10 começa e leva 90 s.
    ultima = await processar_pendentes(None, h(10, 59, 30))
    # Termina 11:01; o laço dorme até a próxima virada...
    despertar = h(11, 1).timestamp() + segundos_ate_proxima_hora(h(11, 1))
    assert despertar < h(12, 1).timestamp()
    # ...e, mesmo que acorde tarde por qualquer motivo, a 11 é recuperada.
    await processar_pendentes(ultima, h(12, 1))

    assert pedidas == [h(10), h(11), h(12)]


async def test_hora_recuperada_leva_a_propria_hora_ao_digest(monkeypatch):
    """A faixa servida é a da hora perdida, não a do relógio no momento da recuperação."""
    horas_do_digest = []

    async def _digest(db, agora=None):
        horas_do_digest.append(agora)
        return {}

    class _Sessao:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return False

    coletas = []

    async def _pipeline(db):
        coletas.append(True)
        return {}

    class _Config:
        news_run_hour = 10

    monkeypatch.setattr(news_agendado.news_digest_service, "enviar_digests", _digest)
    monkeypatch.setattr(news_agendado, "rodar_pipeline", _pipeline)
    monkeypatch.setattr(news_agendado, "get_settings", lambda: _Config())
    monkeypatch.setattr(news_agendado, "async_session_factory", _Sessao)

    await processar_pendentes(h(9), h(11, 5))

    assert horas_do_digest == [h(10), h(11)]
    # A hora da coleta foi a pulada: recuperá-la roda a coleta do dia.
    assert coletas == [True]


async def test_falha_nao_avanca_e_a_hora_e_tentada_de_novo(rodadas):
    pedidas, falhar_em = rodadas
    falhar_em.add(h(11))

    ultima = await processar_pendentes(h(10), h(11, 1))
    assert ultima == h(10), "a hora que falhou não pode contar como servida"

    falhar_em.clear()
    ultima = await processar_pendentes(ultima, h(12, 1))

    assert pedidas == [h(11), h(11), h(12)]
    assert ultima == h(12)
