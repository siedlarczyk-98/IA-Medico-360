"""
Expurgo de retenção rodando dentro do próprio backend.

POR QUE AQUI, E NÃO NUM CRON
O agendamento vivia no painel do Railway — fora do repositório, invisível a
testes, ao CI e a code review. Ele parou de rodar e ninguém soube por 39 dias:
o código continuava correto, a suíte verde, e só o dado vencido acumulava.

Trocar um cron por outro cron não resolveria isso; resolveria só a instância.
Aqui o agendamento é código: aparece no diff, tem teste, e não pode sumir sem
que o backend inteiro caia junto — caso em que a falta de expurgo é o menor dos
problemas.

O QUE ISSO CUSTA
Com várias réplicas, todas rodam o expurgo. É inofensivo: a operação é
idempotente e barata (três UPDATE/DELETE por data), e disputa de escrita entre
réplicas resolve no banco. Trocar isso por eleição de líder seria complexidade
sem ganho nesta escala.

Se o backend ficar fora do ar por dias, o expurgo atrasa junto — e é
justamente isso que o alarme abaixo reporta na volta.
"""

import asyncio
import logging

from app.core.alarme import alarmar
from app.core.database import async_session_factory
from app.models.models import AuditLog
from app.services.data_subject_service import (
    RETENCAO_IMAGEM_DIAS,
    expurgar_dados_vencidos,
    medir_passivo,
)
from app.services.vigilancia_service import ACAO_EXPURGO

logger = logging.getLogger(__name__)

INTERVALO_HORAS = 24

# Espera antes da primeira execução. O boot já carrega modelo de NER e fórmulas;
# somar consulta ao banco na mesma janela atrasaria a primeira requisição.
ATRASO_INICIAL_SEGUNDOS = 90

# Dias de atraso tolerados antes de alarmar. Um dia é ruído normal — deploy,
# reinício, fuso. Acima disso o expurgo deixou de rodar por tempo suficiente
# para significar alguma coisa.
ATRASO_TOLERADO_DIAS = 2


def _alertar(passivo: dict) -> None:
    """
    Reporta atraso ao Sentry, se houver DSN.

    `warning` e não `error`: nada está quebrado neste instante, mas uma política
    de retenção deixou de ser cumprida e alguém precisa olhar. A mecânica do
    envio vive em `app.core.alarme` desde que um segundo alarme precisou dela.
    """
    alarmar(
        tag="expurgo_lgpd",
        mensagem=(
            f"Expurgo LGPD atrasado: {passivo['total']} registros vencidos, "
            f"o mais antigo há {passivo['dias_de_atraso']} dias além do prazo "
            f"de {RETENCAO_IMAGEM_DIAS} dias"
        ),
        contexto=passivo,
    )


async def _uma_rodada() -> None:
    """Mede o atraso ANTES de limpar, senão a evidência some junto com o dado."""
    async with async_session_factory() as db:
        passivo = await medir_passivo(db)

        if passivo["dias_de_atraso"] > ATRASO_TOLERADO_DIAS:
            logger.warning("Expurgo estava atrasado", extra=passivo)
            _alertar(passivo)

        resultado = await expurgar_dados_vencidos(db)

        # Rastro da rodada em `audit_logs`. Sem ele, "quando o expurgo rodou
        # pela última vez?" só tinha resposta na memória de quem estava por
        # perto — e foi assim que 39 dias de silêncio passaram despercebidos.
        # `user_id` e `interaction_id` ficam nulos de propósito: o autor é o
        # próprio sistema, e inventar um usuário sintético sujaria a trilha de
        # auditoria que o mesmo campo serve nas ações de gente de verdade.
        db.add(AuditLog(
            action=ACAO_EXPURGO,
            entity_type="retencao",
            metadata_=resultado,
        ))
        await db.commit()

    logger.info("Expurgo agendado concluído", extra=resultado)


async def _laco() -> None:
    await asyncio.sleep(ATRASO_INICIAL_SEGUNDOS)
    while True:
        try:
            await _uma_rodada()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Uma falha não pode matar o laço: sem isto, um erro transitório de
            # banco encerraria o agendamento em silêncio — exatamente o modo de
            # falha que este módulo existe para eliminar.
            logger.exception("Rodada de expurgo falhou; tentando de novo no próximo ciclo: %s", exc)
        await asyncio.sleep(INTERVALO_HORAS * 3600)


def iniciar() -> asyncio.Task:
    """Dispara o laço em background. Chamado no lifespan da aplicação."""
    logger.info(
        "Expurgo agendado ativo (a cada %dh, primeira rodada em %ds)",
        INTERVALO_HORAS, ATRASO_INICIAL_SEGUNDOS,
    )
    return asyncio.create_task(_laco(), name="expurgo-agendado")


async def parar(tarefa: asyncio.Task | None) -> None:
    """Encerra o laço no shutdown, sem deixar tarefa órfã reclamando no log."""
    if tarefa is None or tarefa.done():
        return
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass
