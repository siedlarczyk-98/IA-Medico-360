"""Médico 360 — Schemas do módulo de Notícias."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nome_pt: str


class TemaCasadoOut(BaseModel):
    """Tema do usuário que casou com o artigo — o 'por que estou vendo isto?'."""

    slug: str
    nome_pt: str


class HighlightOut(BaseModel):
    """
    Item do feed. Sem `rewritten_body`: o corpo responde por ~80% do payload e a
    listagem não o usa — o detalhe é buscado em /articles/{id} ao abrir o card.
    """

    id: int
    journal_slug: str
    rewritten_title: str | None
    # Primeiras linhas em texto puro, para o card. Antes vinha do `excerpt` do
    # WordPress; agora é derivado do corpo. Fica no schema e não numa coluna
    # porque é apresentação, não dado — mudar o tamanho do card não deveria
    # exigir migration nem reprocessar o acervo.
    resumo: str | None
    source_url: str | None
    published_date: datetime | None
    visible_at: datetime | None
    temas: list[TemaCasadoOut] = Field(default_factory=list)
    # A flag que o digest lê para NUNCA interromper alguém por um item que só
    # estava ali para a tela não ficar vazia. Ver `news_feed_service`.
    preenchimento: bool = False


class FeedOut(BaseModel):
    """
    O feed e, quando nada casou, o MOTIVO — para o frontend distinguir
    "não publicaram nada" de "seus temas estão estreitos demais". Tela vazia
    ambígua faz o usuário concluir que o produto morreu.
    """

    itens: list[HighlightOut]
    motivo_vazio: str | None = None


class ArticleDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    journal_slug: str
    rewritten_title: str | None
    rewritten_body: str | None
    source_url: str | None
    doi: str | None
    authors: str | None
    published_date: datetime | None
    visible_at: datetime | None


class MeusTemasOut(BaseModel):
    """
    `selecionados` vazio + `ja_escolheu` False = primeira visita: o frontend
    abre a tela de escolha com `sugeridos` pré-marcados.
    """

    ja_escolheu: bool
    selecionados: list[TemaOut]
    sugeridos: list[TemaOut]
    disponiveis: list[TemaOut]


class MeusTemasIn(BaseModel):
    topic_ids: list[UUID]


class PreferenciasNoticiasIn(BaseModel):
    email: bool


class PreferenciasNoticiasOut(BaseModel):
    email: bool


class FavoritosOut(BaseModel):
    article_ids: list[int]


class FavoritoToggleIn(BaseModel):
    article_id: int


class NaoInteressaIn(BaseModel):
    article_id: int
    topic_slug: str | None = None
