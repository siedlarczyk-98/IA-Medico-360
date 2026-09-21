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

`pg_try_advisory_lock` não espera: quem não pega segue sem o agendador.

## Cuidado ao usar

A conexão é DEDICADA e fica aberta enquanto o processo for líder — é isso que
sustenta o lock. Ela não vem do pool da aplicação (senão ocuparia uma conexão do
pool para sempre); é uma conexão própria, uma por processo.
"""

import logging
from contextlib import asynccontextmanager
from zlib import crc32

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Namespace dos nossos locks. O advisory lock é global no banco — que é
# COMPARTILHADO com o `medico360-news` (ver docs/runbook.md) —, então a chave leva
# um prefixo nosso para não colidir com a de outro serviço.
PREFIXO = "medico360:agendador:"


def chave_do_lock(nome: str) -> int:
    """Nome → inteiro de 64 bits com sinal, que é o que o Postgres aceita."""
    return crc32(f"{PREFIXO}{nome}".encode()) - 2**31


@asynccontextmanager
async def como_lider(nome: str):
    """
    Cede a vez a UM processo. Entrega `True` para o líder e `False` para os outros.

        async with como_lider("expurgo") as sou_lider:
            if sou_lider:
                ...

    Falha ao falar com o banco entrega `False`: sem certeza de exclusividade,
    não se roda. Um ciclo perdido de expurgo é barato; alarme em quádruplo e
    chamada de modelo dobrada, não.
    """
    # Criar o engine DENTRO do try: com a URL malformada ou o driver indisponível,
    # `create_async_engine` levanta na hora — e, fora do try, essa exceção sobe pelo
    # `lifespan` e derruba o boot da aplicação inteira. Um agendador que não sobe é
    # um ciclo perdido; uma API que não sobe é indisponibilidade.
    engine = None
    conexao = None
    sou_lider = False
    try:
        engine = create_async_engine(
            get_settings().database_url,
            # Uma conexão só, que fica aberta enquanto durar a liderança.
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
        )
        conexao = await engine.connect()
        sou_lider = bool(
            (await conexao.execute(
                text("SELECT pg_try_advisory_lock(:chave)"), {"chave": chave_do_lock(nome)}
            )).scalar()
        )
        if sou_lider:
            logger.info("Agendador '%s': este processo é o líder", nome)
        else:
            logger.info("Agendador '%s': outro processo já é o líder; não vou rodar", nome)
        yield sou_lider
    except Exception:
        logger.exception("Agendador '%s': não consegui decidir a liderança; não vou rodar", nome)
        yield False
    finally:
        if conexao is not None:
            # Fechar a conexão já libera o lock (ele é por sessão); o `unlock`
            # explícito é para o caso de o pool reaproveitar a conexão.
            try:
                if sou_lider:
                    await conexao.execute(
                        text("SELECT pg_advisory_unlock(:chave)"), {"chave": chave_do_lock(nome)}
                    )
                await conexao.close()
            except Exception:  # pragma: no cover — encerramento best-effort
                logger.warning("Agendador '%s': falha ao liberar o lock no encerramento", nome)
        if engine is not None:
            await engine.dispose()
