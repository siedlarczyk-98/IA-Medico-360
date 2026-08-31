"""
Médico 360 — Endpoints do módulo de Notícias.

Tudo aqui exige usuário autenticado. A versão anterior identificava o aluno por
`?email=` na query string, sem verificação de posse — aceitável quando o módulo
só listava posts públicos, inviável agora: o feed é personalizado, e um
identificador forjável significaria ler (e alterar) os temas de outra pessoa.
O SSO de embed (`/auth/embed/token`) já resolve identidade dentro do LMS.

Os endpoints administrativos ficam sob checagem de role, e não mais atrás de uma
`ADMIN_API_KEY` própria — uma credencial a menos para vazar.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import User, UserPreference
from app.models.news import (
    Article,
    ArticleStatus,
    Favorite,
    Topic,
    TopicFeedback,
    UserTopic,
)
from app.schemas.news import (
    ArticleDetailOut,
    FavoritosOut,
    FavoritoToggleIn,
    FeedOut,
    HighlightOut,
    MeusTemasIn,
    MeusTemasOut,
    NaoInteressaIn,
    PreferenciasNoticiasIn,
    PreferenciasNoticiasOut,
    TemaCasadoOut,
    TemaOut,
)
from app.services import news_feed_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])

# Teto de favoritos por usuário. Folgado o bastante para não atrapalhar uso real
# — são poucos destaques publicados por semana.
MAX_FAVORITOS = 500

TAMANHO_RESUMO = 240
_TAGS_HTML = re.compile(r"<[^>]+>")


def _resumo(body_html: str | None) -> str | None:
    """
    Texto puro das primeiras linhas do post, para o card da listagem.

    Regex e não um parser de HTML: o corpo é gerado pelo nosso próprio redator,
    com um conjunto restrito de tags (`<p>`, `<strong>`, `<ul>`, `<li>`), e o
    resultado é renderizado como TEXTO no card, nunca como HTML. Um parser aqui
    seria uma dependência a mais para o mesmo resultado.
    """
    if not body_html:
        return None
    texto = _TAGS_HTML.sub(" ", body_html)
    texto = " ".join(texto.split())
    return texto[:TAMANHO_RESUMO] + ("…" if len(texto) > TAMANHO_RESUMO else "")


async def _preferencias(db: AsyncSession, user: User) -> UserPreference:
    prefs = await db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    if prefs is None:
        prefs = UserPreference(user_id=user.id, notification_prefs={}, ui_settings={})
        db.add(prefs)
        await db.flush()
    return prefs


# ── Feed ─────────────────────────────────────────────────────────────────────

@router.get("/highlights", response_model=FeedOut)
async def listar_highlights(
    limite: int = Query(default=30, le=100),
    todos: bool = Query(
        default=False,
        description=(
            "Ignora o filtro por temas e devolve tudo que foi publicado. É a "
            "válvula que impede o filtro de virar caixa-preta."
        ),
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedOut:
    itens, motivo = await news_feed_service.montar_feed(db, user, limite=limite, todos=todos)

    return FeedOut(
        itens=[
            HighlightOut(
                id=i.article.id,
                journal_slug=i.article.journal_slug,
                rewritten_title=i.article.rewritten_title,
                resumo=_resumo(i.article.rewritten_body),
                source_url=i.article.source_url,
                published_date=i.article.published_date,
                visible_at=i.article.visible_at,
                temas=[TemaCasadoOut(slug=s, nome_pt=n) for s, n in i.temas],
                preenchimento=i.preenchimento,
            )
            for i in itens
        ],
        motivo_vazio=motivo,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetailOut)
async def detalhe_artigo(
    article_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Article:
    """
    Corpo do post. Desde que o WordPress saiu, o texto vem daqui — é o mesmo
    conteúdo que já estava no Postgres, agora sem um CMS no meio do caminho.
    """
    article = await db.scalar(
        select(Article).where(
            Article.id == article_id,
            Article.status == ArticleStatus.PUBLISHED.value,
        )
    )
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destaque não encontrado")
    return article


# ── Temas ────────────────────────────────────────────────────────────────────

@router.get("/me/topics", response_model=MeusTemasOut)
async def meus_temas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeusTemasOut:
    selecionados = list(await db.scalars(
        select(Topic)
        .join(UserTopic, UserTopic.topic_id == Topic.id)
        .where(UserTopic.user_id == user.id)
        .order_by(Topic.nome_pt)
    ))
    disponiveis = list(await db.scalars(
        select(Topic).where(Topic.ativo.is_(True)).order_by(Topic.nome_pt)
    ))
    sugeridos = await news_feed_service.temas_sugeridos_para(db, user.specialty)

    prefs = await _preferencias(db, user)
    ja_escolheu = bool((prefs.ui_settings or {}).get("news_topics_escolhidos"))

    return MeusTemasOut(
        ja_escolheu=ja_escolheu,
        selecionados=[TemaOut.model_validate(t) for t in selecionados],
        sugeridos=[TemaOut.model_validate(t) for t in sugeridos],
        disponiveis=[TemaOut.model_validate(t) for t in disponiveis],
    )


@router.put("/me/topics", response_model=MeusTemasOut)
async def salvar_temas(
    body: MeusTemasIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeusTemasOut:
    validos = set(await db.scalars(
        select(Topic.id).where(Topic.id.in_(body.topic_ids), Topic.ativo.is_(True))
    ))

    await db.execute(delete(UserTopic).where(UserTopic.user_id == user.id))
    for topic_id in validos:
        db.add(UserTopic(user_id=user.id, topic_id=topic_id))

    # Marca a primeira escolha. Sem isso não há como distinguir "escolheu nenhum
    # tema de propósito" de "nunca viu a tela" — e o app abriria a escolha
    # de novo a cada visita de quem deliberadamente não quer filtro.
    prefs = await _preferencias(db, user)
    prefs.ui_settings = {**(prefs.ui_settings or {}), "news_topics_escolhidos": True}

    await db.commit()
    return await meus_temas(user=user, db=db)


# ── Preferências de notificação ──────────────────────────────────────────────

@router.get("/me/preferences", response_model=PreferenciasNoticiasOut)
async def ler_preferencias(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PreferenciasNoticiasOut:
    prefs = await _preferencias(db, user)
    return PreferenciasNoticiasOut(
        email=bool((prefs.notification_prefs or {}).get("news", {}).get("email"))
    )


@router.put("/me/preferences", response_model=PreferenciasNoticiasOut)
async def salvar_preferencias(
    body: PreferenciasNoticiasIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PreferenciasNoticiasOut:
    prefs = await _preferencias(db, user)
    atuais = dict(prefs.notification_prefs or {})
    atuais["news"] = {**atuais.get("news", {}), "email": body.email}
    prefs.notification_prefs = atuais
    await db.commit()
    return PreferenciasNoticiasOut(email=body.email)


# ── Favoritos ────────────────────────────────────────────────────────────────

@router.get("/favorites", response_model=FavoritosOut)
async def listar_favoritos(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FavoritosOut:
    ids = list(await db.scalars(select(Favorite.article_id).where(Favorite.user_id == user.id)))
    return FavoritosOut(article_ids=ids)


@router.post("/favorites/toggle", response_model=FavoritosOut)
async def alternar_favorito(
    body: FavoritoToggleIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FavoritosOut:
    existe = await db.scalar(select(Article.id).where(Article.id == body.article_id))
    if not existe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destaque não encontrado")

    atual = await db.scalar(
        select(Favorite.id).where(
            Favorite.user_id == user.id, Favorite.article_id == body.article_id
        )
    )
    if atual:
        await db.execute(delete(Favorite).where(Favorite.id == atual))
    else:
        quantos = len(list(await db.scalars(
            select(Favorite.id).where(Favorite.user_id == user.id)
        )))
        if quantos >= MAX_FAVORITOS:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Limite de favoritos atingido")
        try:
            db.add(Favorite(user_id=user.id, article_id=body.article_id))
            await db.flush()
        except IntegrityError:
            # Corrida rara: outra requisição favoritou no meio tempo. Não é erro
            # para o usuário — o estado final é o que ele pediu.
            await db.rollback()

    await db.commit()
    ids = list(await db.scalars(select(Favorite.article_id).where(Favorite.user_id == user.id)))
    return FavoritosOut(article_ids=ids)


# ── Feedback de relevância ───────────────────────────────────────────────────

@router.post("/feedback/nao-interessa", status_code=status.HTTP_204_NO_CONTENT)
async def nao_interessa(
    body: NaoInteressaIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    "Não é do meu interesse".

    É a única fonte de dado real para corrigir o mapeamento tema<->especialidade.
    Sem ela, ajustar a taxonomia depois seria palpite — e a taxonomia é o que
    define se o filtro acerta ou não.
    """
    topic_id = None
    if body.topic_slug:
        topic_id = await db.scalar(select(Topic.id).where(Topic.slug == body.topic_slug))

    db.add(TopicFeedback(
        user_id=user.id,
        article_id=body.article_id,
        topic_id=topic_id,
        specialty=user.specialty,
    ))
    try:
        await db.commit()
    except IntegrityError:
        # Já havia reclamado deste artigo. Reclamar duas vezes não é erro.
        await db.rollback()


# ── Administração do pipeline ────────────────────────────────────────────────

def _exigir_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Requer perfil administrador")


@router.post("/admin/pipeline")
async def rodar_pipeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dispara coleta + tagging + redação sob demanda, fora do horário agendado."""
    _exigir_admin(user)

    from app.services import news_agendado

    try:
        return await news_agendado.rodar_pipeline(db)
    except Exception:
        logger.exception("Falha ao executar o pipeline de notícias manualmente")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Falha ao executar o pipeline")
