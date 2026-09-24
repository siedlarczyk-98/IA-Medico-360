"""
Eleição de líder: com vários workers, só UM roda os agendadores — e ALGUÉM roda.

Cada worker do uvicorn roda o `lifespan` inteiro. Sem esta trava, quatro workers
alarmariam quatro vezes o mesmo problema (o silêncio de 24h da vigilância é um
dict em memória, por processo) e o pipeline de notícias chamaria o modelo quatro
vezes.

A segunda metade ("alguém roda") é o incidente de 2026-09-24: a primeira versão
tentava o lock só no boot. No deploy o container novo sobe com o antigo ainda
segurando o lock, desiste, e quando o antigo morre ninguém assume. Os testes
antigos cobriam exclusividade e falha do banco; nenhum tinha dois processos com
sobreposição — que é exatamente o que um deploy é.

Conexões REAIS: o advisory lock é por SESSÃO do Postgres, então um teste com
conexão compartilhada não teria o que disputar.
"""

import asyncio

from sqlalchemy import text

from app.core import lider
from app.core.lider import Lideranca, chave_do_lock

# Curto para a suíte não esperar o minuto de produção. O que se testa é a
# REPETIÇÃO da tentativa, não o valor do intervalo.
INTERVALO = 0.05


class Agendadores:
    """Faz o papel dos agendadores do `lifespan`: conta quantas vezes subiu e desceu."""

    def __init__(self) -> None:
        self.subidas = 0
        self.descidas = 0

    @property
    def rodando(self) -> bool:
        return self.subidas > self.descidas

    def subir(self) -> None:
        self.subidas += 1

    async def derrubar(self) -> None:
        self.descidas += 1


def _lideranca(nome: str, agendadores: Agendadores) -> Lideranca:
    return Lideranca(nome, agendadores.subir, agendadores.derrubar, intervalo=INTERVALO)


async def _esperar(condicao, segundos: float = 3.0) -> bool:
    fim = asyncio.get_running_loop().time() + segundos
    while asyncio.get_running_loop().time() < fim:
        if condicao():
            return True
        await asyncio.sleep(0.01)
    return condicao()


async def test_apenas_um_processo_ganha():
    grupos = [Agendadores() for _ in range(4)]
    lideres = [_lideranca("teste-concorrencia", g) for g in grupos]
    await asyncio.gather(*(lid.iniciar() for lid in lideres))
    try:
        # Várias voltas do laço: os seguidores continuam tentando e continuam perdendo.
        await asyncio.sleep(INTERVALO * 5)
        assert sum(lid.sou_lider for lid in lideres) == 1
        assert sum(g.rodando for g in grupos) == 1
    finally:
        await asyncio.gather(*(lid.parar() for lid in lideres))


async def test_deploy_o_processo_novo_assume_quando_o_antigo_sai():
    """
    O incidente, reproduzido: o novo sobe com o antigo segurando o lock, perde a
    primeira tentativa, e PRECISA assumir quando o antigo sai.
    """
    antigo_ag, novo_ag = Agendadores(), Agendadores()
    antigo = _lideranca("teste-deploy", antigo_ag)
    novo = _lideranca("teste-deploy", novo_ag)

    await antigo.iniciar()
    await novo.iniciar()
    try:
        assert antigo.sou_lider and not novo.sou_lider
        assert not novo_ag.rodando

        await antigo.parar()
        assert not antigo_ag.rodando, "o antigo não derrubou os agendadores ao sair"

        assert await _esperar(lambda: novo.sou_lider), (
            "o processo novo não assumiu depois que o antigo saiu — é o deploy que "
            "deixou produção sem expurgo, vigilância e notícias"
        )
        assert novo_ag.rodando
    finally:
        await antigo.parar()
        await novo.parar()


async def test_lider_que_perde_a_conexao_derruba_os_agendadores_e_volta(engine):
    """
    Se a sessão cair, o banco solta o lock e outro processo pode assumir: quem a
    perdeu não pode continuar rodando como se nada fosse.
    """
    agendadores = Agendadores()
    lideranca = _lideranca("teste-queda", agendadores)
    await lideranca.iniciar()
    try:
        assert lideranca.sou_lider and agendadores.subidas == 1
        pid = await lideranca._conexao.scalar(text("SELECT pg_backend_pid()"))

        async with engine.connect() as outra:
            await outra.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

        assert await _esperar(lambda: agendadores.descidas == 1), (
            "a conexão que sustentava o lock caiu e os agendadores continuaram de pé"
        )
        # O lock ficou livre com a queda; o mesmo processo volta a ser o líder.
        assert await _esperar(lambda: agendadores.subidas == 2 and lideranca.sou_lider)
    finally:
        await lideranca.parar()


async def test_banco_fora_do_ar_no_boot_nao_elege_mas_tenta_de_novo(monkeypatch):
    """Sem certeza de exclusividade não se roda — mas a falha não é mais definitiva."""
    real = lider.create_async_engine
    falhas = {"restantes": 2}

    def _instavel(*a, **kw):
        if falhas["restantes"]:
            falhas["restantes"] -= 1
            raise RuntimeError("banco fora do ar")
        return real(*a, **kw)

    monkeypatch.setattr(lider, "create_async_engine", _instavel)

    agendadores = Agendadores()
    lideranca = _lideranca("teste-falha", agendadores)
    await lideranca.iniciar()
    try:
        assert not lideranca.sou_lider and not agendadores.rodando
        assert await _esperar(lambda: lideranca.sou_lider and agendadores.rodando)
    finally:
        await lideranca.parar()


async def test_parar_derruba_os_agendadores_e_devolve_o_lock():
    agendadores = Agendadores()
    primeiro = _lideranca("teste-devolucao", agendadores)
    await primeiro.iniciar()
    await primeiro.parar()
    assert (agendadores.subidas, agendadores.descidas) == (1, 1)

    segundo = _lideranca("teste-devolucao", Agendadores())
    await segundo.iniciar()
    try:
        assert segundo.sou_lider, "o lock não foi devolvido — o próximo deploy esperaria à toa"
    finally:
        await segundo.parar()


async def test_seguidor_que_para_nao_derruba_nada():
    lider_ag, seguidor_ag = Agendadores(), Agendadores()
    dono = _lideranca("teste-seguidor", lider_ag)
    seguidor = _lideranca("teste-seguidor", seguidor_ag)
    await dono.iniciar()
    await seguidor.iniciar()
    await seguidor.parar()
    try:
        assert (seguidor_ag.subidas, seguidor_ag.descidas) == (0, 0)
        assert dono.sou_lider and lider_ag.rodando
    finally:
        await dono.parar()


async def test_falha_ao_subir_os_agendadores_solta_o_lock():
    """Segurar o lock sem agendador de pé só impediria outro processo de rodá-los."""
    def _explode():
        raise RuntimeError("iniciar() quebrou")

    quebrado = Lideranca("teste-subida", _explode, lambda: None, intervalo=3600)
    await quebrado.iniciar()
    try:
        assert not quebrado.sou_lider
        outro = _lideranca("teste-subida", Agendadores())
        await outro.iniciar()
        try:
            assert outro.sou_lider
        finally:
            await outro.parar()
    finally:
        await quebrado.parar()


async def test_agendadores_diferentes_nao_disputam_entre_si():
    a = _lideranca("teste-a", Agendadores())
    b = _lideranca("teste-b", Agendadores())
    await a.iniciar()
    await b.iniciar()
    try:
        assert (a.sou_lider, b.sou_lider) == (True, True)
    finally:
        await a.parar()
        await b.parar()


def test_a_chave_cabe_no_bigint_do_postgres():
    for nome in ("agendadores", "expurgo", "x" * 200, "acentuação"):
        chave = chave_do_lock(nome)
        assert -(2**63) <= chave < 2**63

    assert chave_do_lock("a") != chave_do_lock("b")


async def test_o_lock_e_visivel_no_postgres(db):
    """Prova que é advisory lock de verdade, e não um contador em memória."""
    lideranca = _lideranca("teste-visivel", Agendadores())
    await lideranca.iniciar()
    try:
        assert lideranca.sou_lider
        achados = await db.scalar(text(
            "select count(*) from pg_locks where locktype = 'advisory' and objid = :objid"
        ).bindparams(objid=chave_do_lock("teste-visivel") % 2**32))
    finally:
        await lideranca.parar()

    assert achados >= 1
