"""
Eleição de líder entre processos, com advisory lock do Postgres.

## Por que existe

Com mais de um worker (ou réplica), cada processo roda o `lifespan` inteiro — e
portanto sobe os TRÊS agendadores. O que acontece sem coordenação:

- expurgo de retenção: roda N vezes. É idempotente, então o dano é só trabalho
  repetido;
- vigilância: o silêncio de 24 h por tag é um `dict` EM MEMÓRIA, por processo.
  Quatro workers = quatro alarmes do mesmo problema, todo ciclo. Alarme que grita
  em quádruplo é alarme que se aprende a ignorar;
- notícias: o pipeline chama o modelo. Duas rodadas simultâneas = custo dobrado.
  (O redator já se protege com `skip_locked` e o digest tem unicidade por
  `(user_id, data_ref)`, mas coleta e classificação não têm essa rede.)

## Por que advisory lock, e não Redis

O Redis já é usado para cache e rate limit, e ali ele FALHA ABERTO de propósito —
um Redis fora do ar vira cache miss, não erro. Para eleição de líder, falhar
aberto significa todos os processos se acharem líderes, que é exatamente o que se
quer evitar. O advisory lock do Postgres é amarrado à SESSÃO: se o processo líder
morre, a conexão cai e o lock é liberado pelo banco, sem timeout para ajustar e
sem lock órfão. E o banco é a dependência que a aplicação já não sobrevive sem.

## Por que a eleição NÃO acontece só no boot — o incidente de 2026-09-24

A primeira versão tentava o lock uma vez, no boot, e desistia. Passou em todo
teste e falhou em todo deploy: o Railway sobe o container novo ANTES de derrubar
o antigo, os workers novos encontravam o lock ainda preso, desistiam — e quando o
antigo morria, ninguém assumia. Expurgo LGPD, vigilância e notícias ficaram
parados, e sem alarme, porque o alarme é a vigilância e ela mora no mesmo líder.

Por isso a liderança é uma TAREFA, e não uma decisão: quem não é líder tenta de
novo a cada `INTERVALO_SEGUNDOS`; quem é líder confere a conexão no mesmo ritmo e,
se ela cair, derruba os agendadores e volta a disputar. Um deploy custa, no pior
caso, um intervalo sem agendador.

## Cuidado ao usar

A conexão é DEDICADA e fica aberta só enquanto o processo for líder — é ela que
sustenta o lock. Não vem do pool da aplicação (senão ocuparia uma conexão do pool
para sempre). Quem perde a disputa fecha a conexão na hora: não fica uma ociosa
por worker, como na primeira versão.

Se a conexão do líder cair, o banco solta o lock NA HORA, mas o líder só percebe
na próxima conferência. Nessa janela (até um intervalo) dois processos podem rodar
os agendadores. É o mesmo overlap de qualquer deploy, e os três toleram.
"""

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from zlib import crc32

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Namespace dos nossos locks. O advisory lock é global no banco — que é
# COMPARTILHADO com o `medico360-news` (ver docs/runbook.md) —, então a chave leva
# um prefixo nosso para não colidir com a de outro serviço.
PREFIXO = "medico360:agendador:"

# Quanto um processo espera entre uma tentativa e outra (e o líder, entre uma
# conferência da conexão e outra). É também o pior atraso para alguém assumir
# depois que o líder antigo sai num deploy.
INTERVALO_SEGUNDOS = 60

# Teto de cada ida ao banco. Sem ele, uma rede meio aberta pendura a tarefa — e,
# na primeira tentativa, o boot inteiro.
TIMEOUT_SEGUNDOS = 10


def chave_do_lock(nome: str) -> int:
    """Nome → inteiro de 64 bits com sinal, que é o que o Postgres aceita."""
    return crc32(f"{PREFIXO}{nome}".encode()) - 2**31


async def _chamar(funcao: Callable[[], Awaitable[None] | None]) -> None:
    resultado = funcao()
    if inspect.isawaitable(resultado):
        await resultado


class Lideranca:
    """
    Disputa a liderança `nome` enquanto o processo viver.

        lideranca = Lideranca("agendadores", ao_assumir=subir, ao_perder=derrubar)
        await lideranca.iniciar()   # 1ª tentativa já no boot; as outras, em fundo
        ...
        await lideranca.parar()     # derruba o que subiu e devolve o lock

    `ao_assumir` roda cada vez que este processo vira líder; `ao_perder`, cada vez
    que deixa de ser (conexão caída ou encerramento). Podem ser síncronas ou não.

    Falha ao falar com o banco NÃO elege: sem certeza de exclusividade, não se
    roda. Um ciclo perdido de expurgo é barato; alarme em quádruplo e chamada de
    modelo dobrada, não. A diferença para a primeira versão é que a falha não é
    mais definitiva.
    """

    def __init__(
        self,
        nome: str,
        ao_assumir: Callable[[], Awaitable[None] | None],
        ao_perder: Callable[[], Awaitable[None] | None],
        intervalo: float = INTERVALO_SEGUNDOS,
    ) -> None:
        self.nome = nome
        self._ao_assumir = ao_assumir
        self._ao_perder = ao_perder
        self._intervalo = intervalo
        self._engine: AsyncEngine | None = None
        self._conexao: AsyncConnection | None = None
        self._tarefa: asyncio.Task | None = None
        # Para logar só as MUDANÇAS de estado: um "não sou o líder" a cada minuto,
        # pela vida inteira do processo, enterraria o log.
        self._ultimo_aviso: str | None = None

    @property
    def sou_lider(self) -> bool:
        return self._conexao is not None

    async def iniciar(self) -> None:
        # A primeira tentativa é aguardada: no boot normal (sem deploy em curso) o
        # líder sai decidido junto com a aplicação, como antes.
        await self._tentar_assumir()
        self._tarefa = asyncio.create_task(self._laco(), name=f"lideranca-{self.nome}")

    async def parar(self) -> None:
        if self._tarefa is not None and not self._tarefa.done():
            self._tarefa.cancel()
            try:
                await self._tarefa
            except asyncio.CancelledError:
                pass
        await self._abdicar()

    async def _laco(self) -> None:
        while True:
            await asyncio.sleep(self._intervalo)
            try:
                if self.sou_lider:
                    await self._conferir()
                # Sem `else`: quem acabou de perder a conexão tenta de novo na hora.
                if not self.sou_lider:
                    await self._tentar_assumir()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover — os dois métodos já tratam as suas
                # Esta tarefa não pode morrer: morta, ninguém mais tenta, e é
                # exatamente o incidente que ela existe para evitar.
                logger.exception("Liderança '%s': erro inesperado no laço", self.nome)

    async def _tentar_assumir(self) -> None:
        try:
            await asyncio.wait_for(self._pegar_lock(), TIMEOUT_SEGUNDOS)
        except Exception:
            await self._fechar()
            self._avisar(
                "falha",
                logging.WARNING,
                "Agendador '%s': não consegui falar com o banco para decidir a "
                "liderança; nova tentativa em %ds",
                self.nome,
                int(self._intervalo),
                exc_info=True,
            )
            return

        if not self.sou_lider:
            self._avisar(
                "seguidor",
                logging.INFO,
                "Agendador '%s': outro processo já é o líder; nova tentativa a cada %ds",
                self.nome,
                int(self._intervalo),
            )
            return

        self._avisar("lider", logging.INFO, "Agendador '%s': este processo é o líder", self.nome)
        try:
            await _chamar(self._ao_assumir)
        except Exception:
            # Sem os agendadores de pé, segurar o lock só impediria outro processo
            # de rodá-los. Solta e volta para a fila.
            logger.exception("Agendador '%s': falha ao subir os agendadores; soltando o lock", self.nome)
            await self._abdicar()

    async def _pegar_lock(self) -> None:
        # NullPool: fechar a conexão fecha a sessão de verdade, e com ela o lock.
        self._engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
        conexao = await self._engine.connect()
        try:
            pegou = bool((await conexao.execute(
                text("SELECT pg_try_advisory_lock(:chave)"), {"chave": chave_do_lock(self.nome)}
            )).scalar())
        except BaseException:
            # Inclui o cancelamento do `wait_for`: se o timeout cair DEPOIS de o
            # banco conceder o lock, esta conexão seguraria o lock até o coletor
            # de lixo, e ninguém mais seria líder.
            await asyncio.shield(conexao.close())
            raise
        # A transação implícita do SELECT fica aberta de propósito até o fim: o
        # lock é por sessão, não por transação, então não há o que comitar.
        if pegou:
            self._conexao = conexao
        else:
            await conexao.close()
            await self._fechar()

    async def _conferir(self) -> None:
        """O líder confirma que a sessão que sustenta o lock continua viva."""
        try:
            await asyncio.wait_for(self._conexao.execute(text("SELECT 1")), TIMEOUT_SEGUNDOS)
        except Exception:
            logger.error(
                "Agendador '%s': perdi a conexão que sustentava a liderança; "
                "derrubando os agendadores e voltando a disputar",
                self.nome,
                exc_info=True,
            )
            self._ultimo_aviso = None
            await self._abdicar(soltar_lock=False)

    async def _abdicar(self, soltar_lock: bool = True) -> None:
        if not self.sou_lider:
            await self._fechar()
            return
        try:
            await _chamar(self._ao_perder)
        except Exception:
            logger.exception("Agendador '%s': falha ao derrubar os agendadores", self.nome)
        if soltar_lock:
            # Fechar a conexão já libera o lock; o `unlock` explícito é para o log
            # do Postgres não registrar sessão encerrada segurando lock.
            try:
                await asyncio.wait_for(
                    self._conexao.execute(
                        text("SELECT pg_advisory_unlock(:chave)"), {"chave": chave_do_lock(self.nome)}
                    ),
                    TIMEOUT_SEGUNDOS,
                )
            except Exception:
                logger.warning("Agendador '%s': falha ao soltar o lock no encerramento", self.nome)
        self._ultimo_aviso = None
        await self._fechar()

    async def _fechar(self) -> None:
        """Best-effort: uma conexão já quebrada pode falhar até para fechar."""
        conexao, engine = self._conexao, self._engine
        self._conexao = self._engine = None
        try:
            if conexao is not None:
                await asyncio.wait_for(conexao.close(), TIMEOUT_SEGUNDOS)
        except Exception:
            pass
        try:
            if engine is not None:
                await asyncio.wait_for(engine.dispose(), TIMEOUT_SEGUNDOS)
        except Exception:
            pass

    def _avisar(self, estado: str, nivel: int, mensagem: str, *args, exc_info: bool = False) -> None:
        if estado == self._ultimo_aviso:
            logger.debug(mensagem, *args)
            return
        self._ultimo_aviso = estado
        logger.log(nivel, mensagem, *args, exc_info=exc_info)
