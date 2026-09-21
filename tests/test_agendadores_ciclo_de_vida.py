"""
Os agendadores SOBEM com a aplicação, e descem com ela.

Em 2026-08-27 o expurgo de dados (retenção LGPD) ficou 39 dias parado sem ninguém
saber: o agendamento dependia de um cron externo que deixou de rodar. Ele veio
para dentro do processo (`lifespan`), junto com a vigilância e o pipeline de
notícias — e nenhum teste conferia que o `lifespan` de fato os liga. Um `iniciar()`
apagado num refactor passaria por toda a suíte e só apareceria, de novo, semanas
depois, como dado vencido no banco.
"""

import asyncio

import pytest

from app import main
from app.services import expurgo_agendado, news_agendado, vigilancia_agendada

ESPERADOS = {"expurgo-agendado", "vigilancia-agendada", "noticias-agendado"}


@pytest.fixture(autouse=True)
def lacos_inertes(monkeypatch):
    """Os laços de verdade dormem, consultam o banco e chamam APIs. Aqui só esperam."""
    async def _espera():
        await asyncio.Event().wait()

    for modulo in (expurgo_agendado, vigilancia_agendada, news_agendado):
        monkeypatch.setattr(modulo, "_laco", _espera)
    # Carregar o modelo de NER leva segundos e não é o assunto.
    monkeypatch.setattr(main.ner, "warmup", lambda: True)


def _agendadores_vivos() -> set[str]:
    return {t.get_name() for t in asyncio.all_tasks() if t.get_name() in ESPERADOS and not t.done()}


async def test_o_lifespan_liga_os_tres_agendadores_e_desliga_na_saida():
    assert _agendadores_vivos() == set()

    async with main.app.router.lifespan_context(main.app):
        await asyncio.sleep(0)
        assert _agendadores_vivos() == ESPERADOS, (
            "Agendador que não subiu com a aplicação: "
            f"{sorted(ESPERADOS - _agendadores_vivos())}. Foi assim que o expurgo "
            "ficou 39 dias parado."
        )

    await asyncio.sleep(0)
    assert _agendadores_vivos() == set(), "agendador sobreviveu ao encerramento da aplicação"


async def test_noticias_desligadas_por_configuracao_nao_sobem_e_os_outros_sim(monkeypatch):
    class SemNoticias:
        news_enabled = False

    monkeypatch.setattr(news_agendado, "get_settings", lambda: SemNoticias())

    async with main.app.router.lifespan_context(main.app):
        await asyncio.sleep(0)
        assert _agendadores_vivos() == ESPERADOS - {"noticias-agendado"}


async def test_agendador_que_morre_nao_impede_o_encerramento(monkeypatch):
    """`parar()` com a tarefa já encerrada (por erro) não pode travar o shutdown."""
    async def _morre():
        raise RuntimeError("laço quebrou")

    monkeypatch.setattr(vigilancia_agendada, "_laco", _morre)

    async with main.app.router.lifespan_context(main.app):
        await asyncio.sleep(0.01)

    assert _agendadores_vivos() == set()
