"""
Médico 360 — Montagem do feed personalizado e da seleção de temas.

DOIS LIMIARES, DE PROPÓSITO
Navegar é barato; interromper é caro. O feed usa `news_feed_score_minimo` (o
usuário foi até lá, pode rolar); o digest usa `news_digest_score_minimo`, mais
alto (ele foi até o usuário). O mesmo score que justifica aparecer na lista não
justifica um e-mail.

A REGRA DO FEED VAZIO
A tela nunca fica vazia, e nunca mente sobre o que está mostrando:

  1. Itens que casaram com os temas escolhidos, ordenados por score.
  2. Se casaram menos que `news_feed_minimo_itens`, completa com os melhores dos
     temas `relevante` da especialidade do usuário — marcados `preenchimento=True`.
  3. `motivo_vazio` diz ao frontend QUAL caso é, para a mensagem distinguir
     "não publicaram nada hoje" de "seus temas estão estreitos demais".

Feed vazio ambíguo faz o usuário concluir que o produto morreu. Preenchimento
não marcado faz ele deixar de confiar no filtro. As duas coisas precisam ser
resolvidas juntas — e a marcação NÃO é cosmética: é a flag que o digest lê para
ignorar esses itens (ver `news_digest_service`).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import User
from app.models.news import (
    Article,
    ArticleStatus,
    ArticleTopic,
    Topic,
    TopicSpecialty,
    UserTopic,
)

logger = logging.getLogger(__name__)

# Nenhum destaque publicado na janela — não é problema de filtro.
MOTIVO_SEM_CONTEUDO = "sem_conteudo"
# Há conteúdo, mas nada casou com os temas do usuário.
MOTIVO_SEM_MATCH = "sem_match"


@dataclass
class ItemFeed:
    article: Article
    temas: list[tuple[str, str]]  # [(slug, nome_pt)] que casaram com o usuário
    score: float
    preenchimento: bool


# Piso de sugestão para quem não tem especialidade registrada. Precisa existir:
# o SSO de embed cria o usuário a partir do e-mail do LMS, sem especialidade, e
# ele pode abrir o app de notícias antes de completar o onboarding do app
# principal. Sem piso, esse usuário encara uma lista de 51 caixas em branco —
# exatamente o que a pré-seleção existe para evitar.
ESPECIALIDADE_PISO = "Clínica Médica"


async def temas_sugeridos_para(db: AsyncSession, specialty: str | None) -> list[Topic]:
    """
    Temas `core` + `relevante` da especialidade, para pré-marcar na escolha.

    Sem especialidade — ou com uma que a taxonomia ainda não cobre — devolve os
    temas de Clínica Médica, que é o conjunto generalista.

    O piso NÃO filtra por peso: nenhum tema é `core` de Clínica Médica (ela é a
    especialidade que tangencia tudo e não é dona de nada), então exigir `core`
    aqui devolveria lista vazia. Isso foi descoberto rodando o app: um usuário
    recém-criado pelo embed recebia zero sugestões.
    """
    if specialty:
        rows = list(await db.scalars(
            select(Topic)
            .join(TopicSpecialty, TopicSpecialty.topic_id == Topic.id)
            .where(TopicSpecialty.specialty == specialty, Topic.ativo.is_(True))
            .order_by(Topic.nome_pt)
        ))
        if rows:
            return rows

    return list(await db.scalars(
        select(Topic)
        .join(TopicSpecialty, TopicSpecialty.topic_id == Topic.id)
        .where(TopicSpecialty.specialty == ESPECIALIDADE_PISO, Topic.ativo.is_(True))
        .order_by(Topic.nome_pt)
    ))


async def _artigos_por_temas(
    db: AsyncSession,
    topic_ids: list,
    desde: datetime,
    score_minimo: float,
    limite: int,
    excluir_ids: set[int] | None = None,
) -> list[tuple[Article, float]]:
    """Artigos publicados que casam com os temas dados, com o MAIOR score entre eles."""
    if not topic_ids:
        return []

    condicoes = [
        Article.status == ArticleStatus.PUBLISHED.value,
        Article.visible_at >= desde,
        ArticleTopic.topic_id.in_(topic_ids),
        ArticleTopic.score >= score_minimo,
    ]
    if excluir_ids:
        condicoes.append(Article.id.notin_(excluir_ids))

    stmt = (
        select(Article, func.max(ArticleTopic.score).label("melhor"))
        .join(ArticleTopic, ArticleTopic.article_id == Article.id)
        .where(*condicoes)
        .group_by(Article.id)
        .order_by(func.max(ArticleTopic.score).desc(), Article.visible_at.desc())
        .limit(limite)
    )
    return [(row[0], float(row[1])) for row in (await db.execute(stmt)).all()]


async def _temas_por_artigo(db: AsyncSession, article_ids: list[int], topic_ids: list) -> dict[int, list[tuple[str, str]]]:
    """Quais dos temas DO USUÁRIO casaram com cada artigo — o 'por que estou vendo isto?'."""
    if not article_ids or not topic_ids:
        return {}

    rows = (await db.execute(
        select(ArticleTopic.article_id, Topic.slug, Topic.nome_pt)
        .join(Topic, Topic.id == ArticleTopic.topic_id)
        .where(ArticleTopic.article_id.in_(article_ids), ArticleTopic.topic_id.in_(topic_ids))
        .order_by(ArticleTopic.score.desc())
    )).all()

    mapa: dict[int, list[tuple[str, str]]] = {}
    for article_id, slug, nome in rows:
        mapa.setdefault(article_id, []).append((slug, nome))
    return mapa


async def montar_feed(
    db: AsyncSession,
    user: User,
    limite: int = 30,
    todos: bool = False,
) -> tuple[list[ItemFeed], str | None]:
    """
    Monta o feed do usuário. Retorna (itens, motivo_vazio).

    `todos=True` é a válvula de escape: devolve tudo que foi publicado, sem
    filtro. Sem ela o filtro vira caixa-preta e a primeira reclamação é "sumiu
    conteúdo" — e não haveria como o usuário verificar se sumiu mesmo.
    """
    settings = get_settings()
    desde = datetime.now(UTC) - timedelta(days=settings.news_feed_janela_dias)

    if todos:
        artigos = list(await db.scalars(
            select(Article)
            .where(Article.status == ArticleStatus.PUBLISHED.value, Article.visible_at >= desde)
            .order_by(Article.visible_at.desc())
            .limit(limite)
        ))
        return [ItemFeed(a, [], 0.0, False) for a in artigos], None

    meus_temas = list(await db.scalars(
        select(UserTopic.topic_id).where(UserTopic.user_id == user.id)
    ))

    casados = await _artigos_por_temas(
        db, meus_temas, desde, settings.news_feed_score_minimo, limite
    )
    mapa_temas = await _temas_por_artigo(db, [a.id for a, _ in casados], meus_temas)

    itens = [
        ItemFeed(article=a, temas=mapa_temas.get(a.id, []), score=s, preenchimento=False)
        for a, s in casados
    ]

    # --- Preenchimento ---------------------------------------------------
    if len(itens) < settings.news_feed_minimo_itens:
        adjacentes = list(await db.scalars(
            select(TopicSpecialty.topic_id).where(TopicSpecialty.specialty == user.specialty)
        )) if user.specialty else []

        # Só faz sentido completar com o que o usuário NÃO escolheu; o que ele
        # escolheu já foi buscado acima.
        adjacentes = [t for t in adjacentes if t not in set(meus_temas)]

        complemento = await _artigos_por_temas(
            db,
            adjacentes,
            desde,
            settings.news_feed_score_minimo,
            limite=settings.news_feed_minimo_itens - len(itens),
            excluir_ids={i.article.id for i in itens},
        )
        itens += [
            ItemFeed(article=a, temas=[], score=s, preenchimento=True)
            for a, s in complemento
        ]

    if any(not i.preenchimento for i in itens):
        return itens, None

    # Nada casou de verdade. Distinguir os dois casos é o que permite ao
    # frontend dizer a coisa certa em vez de mostrar uma tela vazia ambígua.
    houve_publicacao = (await db.execute(
        select(func.count())
        .select_from(Article)
        .where(Article.status == ArticleStatus.PUBLISHED.value, Article.visible_at >= desde)
    )).scalar_one()

    motivo = MOTIVO_SEM_MATCH if houve_publicacao else MOTIVO_SEM_CONTEUDO
    return itens, motivo
