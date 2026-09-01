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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.medicina import identidade
from app.models.models import User
from app.models.news import (
    Article,
    ArticleStatus,
    ArticleTopic,
    Topic,
    TopicSpecialty,
    UserTopic,
)
from app.services import news_keyword_service

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
    # Palavras-chave do usuário que casaram com o TEXTO deste artigo. Eixo
    # separado dos temas: ver `news_keyword_service`.
    palavras: list[str] = field(default_factory=list)


# Piso de sugestão para quem não tem especialidade registrada. Precisa existir:
# o SSO de embed cria o usuário a partir do e-mail do LMS, sem especialidade, e
# ele pode abrir o app de notícias antes de completar o onboarding do app
# principal. Sem piso, esse usuário encara uma lista de 51 caixas em branco —
# exatamente o que a pré-seleção existe para evitar.
ESPECIALIDADE_PISO = "Clínica Médica"


async def temas_sugeridos_para(db: AsyncSession, specialties: list[str] | str | None) -> list[Topic]:
    """
    Temas `core` + `relevante` das especialidades, para pré-marcar na escolha.

    Aceita VÁRIAS: duas residências é o caso comum (Clínica Médica é
    pré-requisito de quase toda residência clínica), e um cardiologista que
    também tem Clínica Médica deve receber a união dos dois conjuntos, não a
    de uma delas. `distinct` porque os conjuntos se sobrepõem.

    Sem especialidade — ou com uma que a taxonomia ainda não cobre — devolve os
    temas de Clínica Médica, que é o conjunto generalista.

    O piso NÃO filtra por peso: nenhum tema é `core` de Clínica Médica (ela é a
    especialidade que tangencia tudo e não é dona de nada), então exigir `core`
    aqui devolveria lista vazia. Isso foi descoberto rodando o app: um usuário
    recém-criado pelo embed recebia zero sugestões.
    """
    # Aceita string solta para não quebrar chamadas antigas nem os testes que
    # passam uma especialidade só.
    lista = [specialties] if isinstance(specialties, str) else list(specialties or [])
    if lista:
        rows = list(await db.scalars(
            select(Topic)
            .distinct()
            .join(TopicSpecialty, TopicSpecialty.topic_id == Topic.id)
            .where(TopicSpecialty.specialty.in_(lista), Topic.ativo.is_(True))
            .order_by(Topic.nome_pt)
        ))
        if rows:
            return rows

    # Cair no piso é o sinal de que a identidade não chegou — por webhook, por
    # grupo `[CFM]` ou por onboarding. A CONTAGEM DISTO É A MÉTRICA DE SUCESSO
    # de todo o trabalho de identidade profissional: se ela não cai com o tempo,
    # nada daquilo está funcionando. Antes o piso agia em silêncio e não havia
    # como saber quantos dependiam dele.
    logger.info("news.piso_especialidade origem=%s", "sem_match" if lista else "sem_especialidade")

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

    # --- Palavras-chave -------------------------------------------------
    # ADITIVA, nunca subtrativa: só acrescenta ao que já casou por tema. Se
    # filtrasse, um erro de digitação esvaziaria a tela do usuário.
    #
    # Entra ANTES do preenchimento de propósito: um artigo que casou com um
    # termo que a pessoa escolheu a dedo é conteúdo pedido, não cortesia para a
    # tela não ficar vazia — e, ao contrário do preenchimento, ele pode disparar
    # o digest.
    termos = [k.termo for k in await news_keyword_service.listar(db, user.id)]
    if termos:
        por_palavra = await news_keyword_service.artigos_por_palavras(
            db, termos, desde, limite=limite, excluir_ids={i.article.id for i in itens}
        )
        itens += [
            ItemFeed(article=a, temas=[], score=0.0, preenchimento=False, palavras=p)
            for a, p in por_palavra
        ]

    # --- Preenchimento ---------------------------------------------------
    if len(itens) < settings.news_feed_minimo_itens:
        # TODAS as especialidades do médico, não só a principal: quem tem duas
        # residências deve ser completado com o conjunto das duas.
        rotulos = identidade.rotulos_de_especialidade(user)
        adjacentes = list(await db.scalars(
            select(TopicSpecialty.topic_id).distinct()
            .where(TopicSpecialty.specialty.in_(rotulos))
        )) if rotulos else []

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

# ── Apoio à tela de escolha de temas ─────────────────────────────────────────

ORIGEM_CURADORIA = "curadoria"
ORIGEM_SOCIAL = "social"


async def amostra_por_tema(
    db: AsyncSession, topic_ids: list, por_tema: int = 2
) -> dict:
    """
    Até `por_tema` títulos recentes por tema, para a tela de escolha mostrar o
    que cada tema realmente traria.

    Transforma a tela de uma lista de rótulos abstratos em evidência: o médico
    vê o conteúdo antes de marcar. E um tema que volta VAZIO é informação útil,
    não falha — quer dizer que o tema está quieto, e dizer isso é melhor do que
    deixar a pessoa marcar e esperar por nada.

    Uma query só para todos os temas, via `row_number()`: uma por tema seriam
    dezenas de round-trips contra um banco remoto a cada abertura da tela.
    """
    if not topic_ids:
        return {}

    settings = get_settings()
    desde = datetime.now(UTC) - timedelta(days=settings.news_feed_janela_dias)

    ranqueado = (
        select(
            ArticleTopic.topic_id,
            Article.rewritten_title,
            func.row_number()
            .over(
                partition_by=ArticleTopic.topic_id,
                order_by=Article.visible_at.desc(),
            )
            .label("posicao"),
        )
        .join(Article, Article.id == ArticleTopic.article_id)
        .where(
            Article.status == ArticleStatus.PUBLISHED.value,
            Article.visible_at >= desde,
            ArticleTopic.topic_id.in_(topic_ids),
            ArticleTopic.score >= settings.news_feed_score_minimo,
        )
        .subquery()
    )

    linhas = (await db.execute(
        select(ranqueado.c.topic_id, ranqueado.c.rewritten_title)
        .where(ranqueado.c.posicao <= por_tema)
    )).all()

    amostras: dict = {}
    for topic_id, titulo in linhas:
        if titulo:
            amostras.setdefault(topic_id, []).append(titulo)
    return amostras


async def sugestao_social(db: AsyncSession, specialty: str | None) -> tuple[str, dict]:
    """
    Decide se a tela fala em nome da curadoria ou dos colegas.

    O pedido original era "Os colegas da {especialidade} costumam buscar por".
    Só que no lançamento não existe esse dado: as sugestões saem do nosso
    mapeamento curado, e há zero usuários. Afirmar comportamento de colegas ali
    seria apresentar invenção como fato — para médicos.

    Então a mesma tela troca de texto quando o dado passa a existir:

      curadoria -> "Selecionamos para quem é de Cardiologia"
      social    -> "O que os colegas de Cardiologia mais acompanham", com o
                   percentual real vindo de `news.user_topics`

    A troca é automática, sem deploy. Retorna (origem, {topic_id: percentual}).
    """
    settings = get_settings()
    if not specialty:
        return ORIGEM_CURADORIA, {}

    # Quantos colegas da especialidade já fizeram uma escolha. `distinct` porque
    # cada um tem várias linhas em user_topics.
    colegas = (await db.execute(
        select(func.count(func.distinct(UserTopic.user_id)))
        .join(User, User.id == UserTopic.user_id)
        .where(User.specialty == specialty)
    )).scalar_one()

    if colegas < settings.news_min_amostra_social:
        return ORIGEM_CURADORIA, {}

    linhas = (await db.execute(
        select(UserTopic.topic_id, func.count(func.distinct(UserTopic.user_id)))
        .join(User, User.id == UserTopic.user_id)
        .where(User.specialty == specialty)
        .group_by(UserTopic.topic_id)
    )).all()

    return ORIGEM_SOCIAL, {topic_id: round(quantos / colegas, 2) for topic_id, quantos in linhas}

