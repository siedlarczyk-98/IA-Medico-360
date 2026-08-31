"""
Médico 360 — Modelos do módulo de Notícias (schema `news`).

As tabelas vivem no schema `news` porque o Postgres é compartilhado com os
demais módulos (agregador, calculadoras, landing pages) — mesmo motivo pelo qual
`app/models/calculators.py` usa o schema `calculators`.

CICLO DE VIDA DE UM ARTIGO

    collected            -> item cru salvo pelo Coletor
    tagged               -> Tagger atribuiu temas; pronto para o Redator
    writing              -> Redator pegou o item
    published            -> texto pronto e visível no feed
    skipped_no_abstract  -> terminal, e NÃO é erro: sem abstract não há
                            matéria-prima, e escrever a partir do título solto
                            é o cenário de maior risco de alucinação
    failed               -> alguma etapa falhou; erro em `last_error`

`status` é string simples (não Enum do Postgres) para permitir acrescentar
estados sem `ALTER TYPE` — foi assim que `tagged` e `skipped_no_abstract`
entraram sem migração de tipo.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.models import new_uuid, utcnow

SCHEMA = "news"


class ArticleStatus(str, enum.Enum):
    COLLECTED = "collected"
    TAGGED = "tagged"
    WRITING = "writing"
    PUBLISHED = "published"
    SKIPPED_NO_ABSTRACT = "skipped_no_abstract"
    FAILED = "failed"


# Pesos de `topic_specialties`. `core` é "esta especialidade é dona do tema";
# `relevante` é "interessa, mas não é o território principal" — e é exatamente
# essa distinção que resolve o tema transversal (obesidade é `core` de
# Endocrinologia e `relevante` de Cardiologia, sem nenhum caso especial em código).
PESO_CORE = "core"
PESO_RELEVANTE = "relevante"


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        # Idempotência: o coletor pode rodar 2x no mesmo dia sem duplicar.
        UniqueConstraint("source", "external_id", name="uq_articles_source_external_id"),
        Index("ix_articles_status", "status"),
        Index("ix_articles_status_published_date", "status", "published_date"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # --- Origem ---
    journal_slug: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # "pubmed"
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)  # PMID
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # --- Conteúdo original (coletado) ---
    original_title: Mapped[str] = mapped_column(Text, nullable=False)
    original_abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)  # separados por "; "
    published_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Descritores MeSH do PubMed, quando houver. Sinal SECUNDÁRIO para o tagger:
    # a indexação MEDLINE atrasa e a janela de coleta é de 10 dias, então a
    # maioria dos artigos recém-coletados ainda está ahead-of-print, sem MeSH.
    # Formato: [{"descriptor": "Obesity", "major": true}, ...]
    mesh_terms: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # --- Conteúdo gerado (redator) ---
    rewritten_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewritten_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Publicação ---
    # Quando o item passou a ser visível no feed. Distinto de `published_date`,
    # que é a data em que o JOURNAL publicou o paper.
    visible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Registro histórico do tempo em que o módulo publicava no WordPress. Ficam
    # nullable e sem uso novo: apagar perderia o rastro de posts que foram ao ar.
    wp_post_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wp_post_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # --- Controle de fluxo ---
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=ArticleStatus.COLLECTED.value)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    topics: Mapped[list["ArticleTopic"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class Topic(Base):
    """
    Vocabulário CONTROLADO de temas. É o que o usuário escolhe e o que o tagger
    pode atribuir.

    Ser fechado é o ponto: com tema livre, o LLM produz "IC", "insuficiência
    cardíaca" e "ICFEr" como três temas distintos, e o casamento com a escolha
    do usuário deixa de funcionar.
    """

    __tablename__ = "topics"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    nome_pt: Mapped[str] = mapped_column(String(160), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    especialidades: Mapped[list["TopicSpecialty"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class TopicSpecialty(Base):
    """
    Tema <-> especialidade, com peso. A tabela que resolve o tema transversal:
    um tema simplesmente tem várias linhas, uma por especialidade interessada.

    `specialty` é string e não FK porque a especialidade do usuário mora em
    `users.specialty` como texto livre vindo da lista do onboarding — criar uma
    FK aqui exigiria normalizar aquela coluna primeiro, o que é uma migração de
    dado independente deste módulo.
    """

    __tablename__ = "topic_specialties"
    __table_args__ = (
        UniqueConstraint("topic_id", "specialty", name="uq_topic_specialties_topic_specialty"),
        Index("ix_topic_specialties_specialty", "specialty"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.topics.id", ondelete="CASCADE"), nullable=False
    )
    specialty: Mapped[str] = mapped_column(String(120), nullable=False)
    peso: Mapped[str] = mapped_column(String(20), nullable=False, default=PESO_RELEVANTE)

    topic: Mapped["Topic"] = relationship(back_populates="especialidades")


class ArticleTopic(Base):
    """Tema atribuído a um artigo, com score e procedência (`llm` ou `mesh`)."""

    __tablename__ = "article_topics"
    __table_args__ = (
        UniqueConstraint("article_id", "topic_id", name="uq_article_topics_article_topic"),
        Index("ix_article_topics_topic_score", "topic_id", "score"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    article_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.topics.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    origem: Mapped[str] = mapped_column(String(10), nullable=False, default="llm")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    article: Mapped["Article"] = relationship(back_populates="topics")
    topic: Mapped["Topic"] = relationship()


class UserTopic(Base):
    """Tema escolhido pelo usuário. Pré-populado pela especialidade, editável por ele."""

    __tablename__ = "user_topics"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_user_topics_user_topic"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.topics.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Favorite(Base):
    """Favorito de um usuário sobre um artigo publicado."""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_favorites_user_article"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TopicFeedback(Base):
    """
    "Não é do meu interesse", clicado num card.

    Uma tabela e um botão, e é a ÚNICA fonte de dado real para corrigir o
    mapeamento tema<->especialidade depois. Sem isso, ajustar a taxonomia vira
    palpite — e a taxonomia é o que define se o produto acerta ou não.

    `specialty` é copiada no momento do clique de propósito: se o usuário mudar
    de especialidade depois, o feedback continua dizendo o que era verdade
    quando ele reclamou.
    """

    __tablename__ = "topic_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "article_id", name="uq_topic_feedback_user_article"),
        Index("ix_topic_feedback_topic", "topic_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.topics.id", ondelete="SET NULL"), nullable=True
    )
    specialty: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DigestSend(Base):
    """
    Registro de digest enviado. Existe para IDEMPOTÊNCIA, não para relatório.

    Sem esta tabela, um retry da tarefa diária manda o mesmo digest duas vezes —
    e o segundo e-mail é exatamente o ruído que este módulo inteiro existe para
    eliminar. A unicidade (user_id, data_ref) é a garantia, não uma conveniência.
    """

    __tablename__ = "digest_sends"
    __table_args__ = (
        UniqueConstraint("user_id", "data_ref", name="uq_digest_sends_user_data"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    data_ref: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    article_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    enviado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
