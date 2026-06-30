"""
Médico 360 — Modelos do módulo de Calculadoras Científicas (schema `calculators`).
Ver Calculadoras_Cientificas_Regras_de_Arquitetura_v1.0.md.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
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

SCHEMA = "calculators"


class EngineTypeEnum(str, enum.Enum):
    FORMULA = "formula"
    ORCHESTRATOR = "orchestrator"


class CalculatorStatusEnum(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class Specialty(Base):
    __tablename__ = "specialties"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    calculators: Mapped[list["CalculatorDefinition"]] = relationship(back_populates="specialty")


class CalculatorDefinition(Base):
    __tablename__ = "calculator_definitions"
    __table_args__ = (
        Index("ix_calculator_definitions_specialty_status", "specialty_id", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    specialty_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.specialties.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    engine_type: Mapped[str] = mapped_column(String(20), nullable=False, default=EngineTypeEnum.FORMULA.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CalculatorStatusEnum.ACTIVE.value)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    specialty: Mapped["Specialty"] = relationship(back_populates="calculators")
    fields: Mapped[list["CalculatorField"]] = relationship(back_populates="calculator", cascade="all, delete-orphan")
    versions: Mapped[list["CalculatorVersion"]] = relationship(back_populates="calculator", cascade="all, delete-orphan")
    executions: Mapped[list["CalculatorExecution"]] = relationship(back_populates="calculator")


class CalculatorField(Base):
    __tablename__ = "calculator_fields"
    __table_args__ = (
        UniqueConstraint("calculator_id", "key", name="uq_calculator_fields_calculator_key"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    calculator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.calculator_definitions.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(30))
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_value: Mapped[float | None] = mapped_column()
    max_value: Mapped[float | None] = mapped_column()
    options: Mapped[list | None] = mapped_column(JSONB)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updatedat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    calculator: Mapped["CalculatorDefinition"] = relationship(back_populates="fields")


class CalculatorVersion(Base):
    __tablename__ = "calculator_versions"
    __table_args__ = (
        UniqueConstraint("calculator_id", "version_number", name="uq_calculator_versions_calculator_version"),
        Index("ix_calculator_versions_calculator_active", "calculator_id", "is_active"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    calculator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.calculator_definitions.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    formula_key: Mapped[str] = mapped_column(String(150), nullable=False)
    interpretation_rules: Mapped[dict | None] = mapped_column(JSONB)
    clinical_reference: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    calculator: Mapped["CalculatorDefinition"] = relationship(back_populates="versions")
    executions: Mapped[list["CalculatorExecution"]] = relationship(back_populates="version")


class CalculatorExecution(Base):
    __tablename__ = "calculator_executions"
    __table_args__ = (
        Index("ix_calculator_executions_user_createdat", "user_id", "createdat"),
        Index("ix_calculator_executions_calculator_user", "calculator_id", "user_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    calculator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.calculator_definitions.id"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(f"{SCHEMA}.calculator_versions.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.id"))
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interactions.id"), nullable=True)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    interpretation: Mapped[str | None] = mapped_column(Text)
    createdat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    calculator: Mapped["CalculatorDefinition"] = relationship(back_populates="executions")
    version: Mapped["CalculatorVersion"] = relationship(back_populates="executions")
