"""
Médico 360 — Modelos SQLAlchemy baseados no ERD (medico360_erd_final.mermaid).
Cobre todas as entidades necessárias para o Agregador + auditoria.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Helpers ──────────────────────────────────────────────────

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── Enums ────────────────────────────────────────────────────

import enum

class FeatureEnum(str, enum.Enum):
    AGREGADOR = "AGREGADOR"
    ORQUESTRADOR = "ORQUESTRADOR"


class ModeEnum(str, enum.Enum):
    BIZU = "BIZU"
    SHERLOCK = "SHERLOCK"
    FARMACIA = "FARMACIA"
    INTERACOES = "INTERACOES"
    PRODUTIVIDADE = "PRODUTIVIDADE"


class InputTypeEnum(str, enum.Enum):
    TEXT = "TEXT"
    AUDIO = "AUDIO"


# ── Company - ok ──────────────────────────────────────────────────

class Company(Base):
    __tablename__ = "company"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    company_status: Mapped[bool] = mapped_column(Boolean, default=True)
    legacy_company_id: Mapped[str | None] = mapped_column(String(255))
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="company")


# ── User - ok ─────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    phone_number: Mapped[str | None] = mapped_column(String(20))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.id"))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    crm: Mapped[str] = mapped_column(String(20), nullable=False)
    crm_state: Mapped[str] = mapped_column(String(2), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="free_user")
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    legacy_user_id: Mapped[str | None] = mapped_column(String(255))
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    company: Mapped["Company | None"] = relationship(back_populates="users")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    preferences: Mapped["UserPreference | None"] = relationship(back_populates="user", uselist=False)


# ── User Preferences - ok ─────────────────────────────────────

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    selected_models: Mapped[dict | None] = mapped_column(JSONB, default=list)
    ui_settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    notification_prefs: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="preferences")


# ── Conversation - ok ────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="conversations")
    interactions: Mapped[list["Interaction"]] = relationship(back_populates="conversation")


# ── Interaction - ok ─────────────────────────────────────────────

class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.id"))
    feature: Mapped[str] = mapped_column(String(50), nullable=False)
    mode: Mapped[str | None] = mapped_column(String(50))
    input_type: Mapped[str] = mapped_column(String(20), default="TEXT")
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_sanitized: Mapped[bool] = mapped_column(Boolean, default=False)
    triage_confidence: Mapped[float | None] = mapped_column(Float)
    triage_category: Mapped[str | None] = mapped_column(String(50))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    token_cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    specialty_detected: Mapped[str | None] = mapped_column(String(100))
    topic_detected: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(back_populates="interactions")
    responses: Mapped[list["InteractionResponse"]] = relationship(back_populates="interaction")
    pharma_alerts: Mapped[list["PharmaAlert"]] = relationship(back_populates="interaction")
    medications: Mapped[list["InteractionMedication"]] = relationship(back_populates="interaction")
    pubmed_validations: Mapped[list["PubmedValidation"]] = relationship(back_populates="interaction")


# ── Interaction Response - ok ─────────────────────────────────────

class InteractionResponse(Base):
    __tablename__ = "interaction_responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interactions.id"), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    interaction: Mapped["Interaction"] = relationship(back_populates="responses")


# ── Pharma Alert - ok ────────────────────────────────────────────

class PharmaAlert(Base):
    __tablename__ = "pharma_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interactions.id"), nullable=False)
    alert_level: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_color: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_api: Mapped[str] = mapped_column(String(50))
    doctor_justification: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    interaction: Mapped["Interaction"] = relationship(back_populates="pharma_alerts")


# ── Interaction Medication - ok ───────────────────────────────────

class InteractionMedication(Base):
    __tablename__ = "interaction_medications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interactions.id"), nullable=False)
    medication_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    medication_normalized: Mapped[str | None] = mapped_column(String(255))
    atc_code: Mapped[str | None] = mapped_column(String(50))
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(20), default="prompt")

    # Relationships
    interaction: Mapped["Interaction"] = relationship(back_populates="medications")


# ── PubMed Validation - ok ────────────────────────────────────────

class PubmedValidation(Base):
    __tablename__ = "pubmed_validations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interactions.id"), nullable=False)
    pmid: Mapped[str] = mapped_column(String(20), nullable=False)
    article_title: Mapped[str | None] = mapped_column(Text)
    abstract_snippet: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    interaction: Mapped["Interaction"] = relationship(back_populates="pubmed_validations")


# ── Audit Log ────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interactions.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(100))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── Consent Log ──────────────────────────────────────────────

class ConsentLog(Base):
    __tablename__ = "consent_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# ── Pricing AI Models ──────────────────────────────────────────────

class ModelPricing(Base):
    __tablename__ = "model_pricing"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    model_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ── Semantic Cache ────────────────────────────────────────────

class SemanticCache(Base):
    __tablename__ = "semantic_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_embedding: Mapped[list] = mapped_column(Vector(1536), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)