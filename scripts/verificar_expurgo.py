"""
Alarme: o expurgo de dados vencidos está mesmo rodando?

Não apaga nada — só conta o que já passou do prazo e continua no banco.

    python -m scripts.expurgar_dados_vencidos    # apaga
    python -m scripts.verificar_expurgo          # confere e alarma

Sai com código 1 quando encontra passivo, e reporta ao Sentry se houver DSN
configurado.

POR QUE ISTO EXISTE
A política de retenção (LGPD art. 16) está implementada em
`data_subject_service` e agendada por cron no painel do Railway — fora do
repositório. O Railway não notifica falha de cron, então um agendamento
removido, pausado ou mal configurado não avisa ninguém: o código continua
correto, os testes continuam verdes, e só o dado vencido se acumula.

Foi exatamente o que aconteceu. Em 2026-08-27 havia 14 imagens além dos 30 dias
ainda com o base64 no banco, e 8 já expurgadas — a assinatura de um job que
rodou uma vez e nunca mais.

Uma hipótese que encaixa nos fatos e vale conferir no painel: se o Cron Schedule
tiver sido posto no serviço do BACKEND, o Railway executa o CMD do Dockerfile
(uvicorn), que nunca encerra — e o Railway pula toda execução seguinte porque "a
anterior ainda está rodando". Cron do Railway precisa de um serviço próprio, cujo
comando termine.

COMO AGENDAR
Serviço separado, mesmo repositório, start command
`python -m scripts.expurgar_dados_vencidos`, Cron Schedule em UTC. E um segundo
serviço rodando ESTE script algumas horas depois, para alarmar se o primeiro não
tiver feito efeito.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.error_tracking import setup_sentry
from app.core.logging_config import setup_logging
from app.models.models import FileExtraction
from app.services.data_subject_service import (
    RETENCAO_ARQUIVO_DIAS,
    RETENCAO_IMAGEM_DIAS,
)

logger = logging.getLogger("scripts.verificar_expurgo")


def _limite(dias: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=dias)


async def medir_passivo() -> dict:
    """Conta o que passou do prazo e ainda está no banco."""
    async with async_session_factory() as db:
        imagens = (await db.execute(
            select(func.count())
            .select_from(FileExtraction)
            .where(
                FileExtraction.image_base64.is_not(None),
                FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
            )
        )).scalar_one()

        arquivos = (await db.execute(
            select(func.count())
            .select_from(FileExtraction)
            .where(FileExtraction.created_at < _limite(RETENCAO_ARQUIVO_DIAS))
        )).scalar_one()

        mais_antigo = (await db.execute(
            select(func.min(FileExtraction.created_at)).where(
                FileExtraction.image_base64.is_not(None),
                FileExtraction.created_at < _limite(RETENCAO_IMAGEM_DIAS),
            )
        )).scalar_one()

    atraso = 0
    if mais_antigo:
        atraso = (datetime.now(UTC) - mais_antigo).days - RETENCAO_IMAGEM_DIAS

    return {
        "imagens_vencidas": imagens,
        "arquivos_vencidos": arquivos,
        "dias_de_atraso": max(atraso, 0),
        "total": imagens + arquivos,
    }


def _alertar_sentry(passivo: dict) -> bool:
    """
    Reporta o passivo como evento no Sentry.

    Sem DSN configurado é no-op, igual ao resto do projeto — em desenvolvimento
    o print no terminal basta. Reusa `setup_sentry` de propósito: ele já aplica
    o scrubbing de PII, e um `sentry_sdk.init` próprio aqui contornaria isso.
    """
    settings = get_settings()
    if not setup_sentry(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.sentry_release or None,
    ):
        return False

    import sentry_sdk

    # `warning` e não `error`: nada está quebrado neste instante, mas uma
    # política de retenção deixou de ser cumprida e alguém precisa agir.
    with sentry_sdk.push_scope() as scope:
        scope.set_level("warning")
        scope.set_tag("alarme", "expurgo_lgpd")
        # Sem contexto, o evento vira "algo está errado" e ninguém sabe o quê.
        scope.set_context("passivo", passivo)
        sentry_sdk.capture_message(
            f"Expurgo LGPD atrasado: {passivo['total']} registros vencidos, "
            f"o mais antigo há {passivo['dias_de_atraso']} dias além do prazo"
        )
    sentry_sdk.flush(timeout=5)
    return True


async def main() -> int:
    settings = get_settings()
    setup_logging(level=settings.log_level, json_output=settings.is_production)

    passivo = await medir_passivo()

    print("Passivo de expurgo (LGPD art. 16)\n")
    print(f"  imagens além de {RETENCAO_IMAGEM_DIAS} dias com base64 : {passivo['imagens_vencidas']}")
    print(f"  arquivos além de {RETENCAO_ARQUIVO_DIAS} dias           : {passivo['arquivos_vencidos']}")

    if passivo["total"] == 0:
        print("\nOK — nada vencido. O expurgo está em dia.")
        logger.info("Expurgo em dia", extra=passivo)
        return 0

    print(f"\n  atraso do registro mais antigo: {passivo['dias_de_atraso']} dias além do prazo")
    print("\nPASSIVO ENCONTRADO — o cron provavelmente não está rodando.")
    print("Confira o agendamento no painel do Railway e rode:")
    print("    python -m scripts.expurgar_dados_vencidos")

    logger.warning("Expurgo atrasado", extra=passivo)

    if _alertar_sentry(passivo):
        print("\nAlerta enviado ao Sentry.")
    else:
        print("\nSentry sem DSN configurado — alerta não enviado.")

    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
