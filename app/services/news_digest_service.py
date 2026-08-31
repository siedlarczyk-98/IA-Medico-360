"""
Médico 360 — Digest diário de notícias por e-mail.

REGRAS QUE NÃO SÃO NEGOCIÁVEIS

1. Zero match real ⇒ zero e-mail. A queixa que originou o módulo é sobre ruído;
   mandar "não temos nada para você hoje" seria produzir exatamente o ruído que
   estamos removendo.

2. Item de PREENCHIMENTO nunca entra. O feed completa a tela com temas adjacentes
   para não deixá-la vazia (ver `news_feed_service`), mas aquilo é cortesia de
   navegação, não motivo de interrupção. Aqui só conta o que casou com os temas
   que o usuário escolheu — por isso este módulo NÃO reusa `montar_feed`, e sim
   consulta os temas do usuário direto.

3. Limiar mais alto que o do feed (`news_digest_score_minimo`). Navegar é barato,
   interromper é caro.

4. Idempotência via `news.digest_sends`. Sem ela, um retry manda o mesmo digest
   duas vezes — e o segundo e-mail é o ruído que tudo isto existe para evitar.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import AuditLog, User, UserPreference
from app.models.news import (
    Article,
    ArticleStatus,
    ArticleTopic,
    DigestSend,
    UserTopic,
)
from app.services import email_service
from app.services.vigilancia_service import ACAO_DIGEST_NOTICIAS

logger = logging.getLogger(__name__)

# Teto de artigos por e-mail. Um digest longo demais não é lido, e o objetivo é
# leitura, não cobertura.
MAX_ARTIGOS_POR_DIGEST = 8


def quer_digest(prefs: UserPreference | None) -> bool:
    """
    Lê `notification_prefs.news.email`. Ausente = False.

    Opt-in explícito e não opt-out: ninguém passa a receber e-mail por efeito
    colateral de um deploy nosso.
    """
    if prefs is None or not prefs.notification_prefs:
        return False
    return bool(prefs.notification_prefs.get("news", {}).get("email"))


async def _artigos_do_usuario(db: AsyncSession, user_id, desde: datetime) -> list[Article]:
    """Artigos que casam com os temas ESCOLHIDOS pelo usuário, acima do limiar do digest."""
    settings = get_settings()

    meus_temas = select(UserTopic.topic_id).where(UserTopic.user_id == user_id).scalar_subquery()

    stmt = (
        select(Article)
        .join(ArticleTopic, ArticleTopic.article_id == Article.id)
        .where(
            Article.status == ArticleStatus.PUBLISHED.value,
            Article.visible_at >= desde,
            ArticleTopic.topic_id.in_(meus_temas),
            ArticleTopic.score >= settings.news_digest_score_minimo,
        )
        .group_by(Article.id)
        .order_by(func.max(ArticleTopic.score).desc(), Article.visible_at.desc())
        .limit(MAX_ARTIGOS_POR_DIGEST)
    )
    return list((await db.execute(stmt)).scalars())


async def enviar_digests(db: AsyncSession, agora: datetime | None = None) -> dict:
    """
    Uma rodada de digest. Retorna resumo para log e para a vigilância.

    `agora` é injetável para teste — sem isso, testar a janela exigiria mexer no
    relógio do processo.
    """
    settings = get_settings()
    agora = agora or datetime.now(UTC)
    data_ref = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    desde = agora - timedelta(days=settings.news_digest_janela_dias)

    candidatos = (await db.execute(
        select(User, UserPreference)
        .join(UserPreference, UserPreference.user_id == User.id)
        .where(User.status.is_(True))
    )).all()

    enviados, sem_conteudo, ja_enviados, falhas = 0, 0, 0, 0

    for user, prefs in candidatos:
        if not quer_digest(prefs):
            continue

        ja = await db.scalar(
            select(DigestSend.id).where(
                DigestSend.user_id == user.id, DigestSend.data_ref == data_ref
            )
        )
        if ja:
            ja_enviados += 1
            continue

        artigos = await _artigos_do_usuario(db, user.id, desde)
        if not artigos:
            # O caso mais comum e o mais importante: silêncio é a resposta certa.
            sem_conteudo += 1
            continue

        # Grava ANTES de enviar. Se o envio falhar, o usuário perde um digest;
        # se gravássemos depois, uma queda entre envio e commit mandaria o mesmo
        # e-mail de novo na próxima rodada. Entre perder um e duplicar um, num
        # produto cuja premissa é não incomodar, perder é o erro barato.
        db.add(DigestSend(
            user_id=user.id,
            data_ref=data_ref,
            article_ids=[a.id for a in artigos],
        ))
        try:
            await db.flush()
        except IntegrityError:
            # Outra réplica ganhou a corrida. Não é erro: é a idempotência
            # funcionando exatamente como projetada.
            await db.rollback()
            ja_enviados += 1
            continue

        try:
            await email_service.send_news_digest(user.email, user.name, artigos)
            enviados += 1
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao enviar digest para user_id=%s", user.id)
            falhas += 1

    resumo = {
        "enviados": enviados,
        "sem_conteudo": sem_conteudo,
        "ja_enviados": ja_enviados,
        "falhas": falhas,
    }

    # HEARTBEAT — e não estatística.
    # "Zero envios" é o comportamento CORRETO num dia em que nada casou, e é
    # indistinguível de "a tarefa morreu". Sem este rastro, a única evidência de
    # que o digest roda seriam os envios — e justamente nos dias silenciosos,
    # que são a maioria, não haveria evidência nenhuma. Mesmo mecanismo que
    # `ACAO_EXPURGO` usa desde que 39 dias de silêncio passaram despercebidos.
    db.add(AuditLog(
        action=ACAO_DIGEST_NOTICIAS,
        entity_type="noticias",
        metadata_=resumo,
    ))
    await db.commit()

    logger.info("Digest de notícias concluído", extra=resumo)
    return resumo
