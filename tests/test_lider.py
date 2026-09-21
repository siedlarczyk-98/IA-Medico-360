"""
Eleição de líder: com vários workers, só UM roda os agendadores.

Cada worker do uvicorn roda o `lifespan` inteiro. Sem esta trava, quatro workers
alarmariam quatro vezes o mesmo problema (o silêncio de 24h da vigilância é um
dict em memória, por processo) e o pipeline de notícias chamaria o modelo quatro
vezes. É o pré-requisito que faltava para usar as 8 vCPU da máquina.

Conexões REAIS: o advisory lock é por SESSÃO do Postgres, então um teste com
conexão compartilhada não teria o que disputar.
"""

import asyncio

from sqlalchemy import text

from app.core.lider import chave_do_lock, como_lider


async def _lideres_entre(n: int) -> int:
    """Quantos, de `n` processos concorrentes, se acham líderes."""
    async def tentar() -> bool:
        async with como_lider("teste-concorrencia") as sou_lider:
            if sou_lider:
                await asyncio.sleep(0.3)  # segura a liderança enquanto os outros tentam
            return sou_lider

    return sum(await asyncio.gather(*(tentar() for _ in range(n))))


async def test_apenas_um_processo_ganha():
    assert await _lideres_entre(4) == 1


async def test_a_lideranca_e_devolvida_ao_sair():
    """Sem isto, um deploy deixaria o lock preso e nenhum processo novo rodaria."""
    async with como_lider("teste-devolucao") as primeiro:
        assert primeiro is True

    async with como_lider("teste-devolucao") as segundo:
        assert segundo is True, "o lock não foi liberado — nenhum agendador voltaria a subir"


async def test_agendadores_diferentes_nao_disputam_entre_si():
    async with como_lider("teste-a") as a, como_lider("teste-b") as b:
        assert (a, b) == (True, True)


async def test_falha_no_banco_nao_elege_ninguem(monkeypatch):
    """Sem certeza de exclusividade, não se roda: é o oposto de falhar aberto."""
    def _explode(*_a, **_kw):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr("app.core.lider.create_async_engine", _explode)

    async with como_lider("teste-falha") as sou_lider:
        assert sou_lider is False


def test_a_chave_cabe_no_bigint_do_postgres():
    for nome in ("agendadores", "expurgo", "x" * 200, "acentuação"):
        chave = chave_do_lock(nome)
        assert -(2**63) <= chave < 2**63

    assert chave_do_lock("a") != chave_do_lock("b")


async def test_o_lock_e_visivel_no_postgres(db):
    """Prova que é advisory lock de verdade, e não um contador em memória."""
    async with como_lider("teste-visivel") as sou_lider:
        assert sou_lider
        achados = await db.scalar(text(
            "select count(*) from pg_locks where locktype = 'advisory' and objid = :objid"
        ).bindparams(objid=chave_do_lock("teste-visivel") % 2**32))

    assert achados >= 1
