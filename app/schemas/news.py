"""Médico 360 — Schemas do módulo de Notícias."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TemaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    nome_pt: str


class TemaSugeridoOut(BaseModel):
    """Tema sugerido, com uma amostra do que ele traria (usada no hover)."""

    id: UUID
    slug: str
    nome_pt: str
    # Títulos reais que o tema traria, para o hover na tela de escolha. Vazio
    # NÃO é falha: quer dizer que o tema não teve destaque na janela.
    amostra: list[str] = Field(default_factory=list)
    # Fração de colegas da especialidade que acompanham este tema. Só vem
    # preenchido quando há amostra suficiente — ver `sugestao_social`.
    percentual: float | None = None


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
    # Palavras-chave do usuário que casaram com o texto deste artigo. Eixo
    # separado dos temas — o card mostra as duas coisas de formas distintas.
    palavras: list[str] = Field(default_factory=list)
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
    sugeridos: list[TemaSugeridoOut]
    disponiveis: list[TemaOut]
    # "curadoria" ou "social". Decide a frase de abertura da tela: enquanto não
    # há colegas suficientes da especialidade, afirmar o que eles acompanham
    # seria estatística inventada. Ver `news_feed_service.sugestao_social`.
    origem_sugestao: str
    especialidade: str | None = None
    # Primeiro nome, para a tela cumprimentar a pessoa. Pode ser None: o SSO de
    # embed cria o usuário só com e-mail, e o nome só existe para quem passou
    # pelo onboarding do app principal. A tela precisa funcionar sem ele.
    primeiro_nome: str | None = None


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


class PalavraChaveOut(BaseModel):
    termo: str
    # Quantos destaques o termo traz na janela atual. É o que impede a palavra-
    # chave de ser um ato de fé: um termo que não casa com nada fica visível
    # como tal, em vez de o usuário concluir dias depois que o produto quebrou.
    destaques: int


class PalavraChaveIn(BaseModel):
    termo: str


class PreviaPalavraChaveOut(BaseModel):
    termo: str
    destaques: int
