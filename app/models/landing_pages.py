"""
Médico 360 — Modelos de captação das landing pages (schema `landing_pages`).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.models import new_uuid, utcnow

SCHEMA = "landing_pages"


class LandingPage(Base):
    __tablename__ = "landing_pages"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submissions: Mapped[list["Submission"]] = relationship(back_populates="landing_page")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_email", "email"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    landing_page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.landing_pages.id", ondelete="RESTRICT"), nullable=False
    )
    # Preenchido quando a submissao vem de dentro do produto (medico logado).
    # Fica nulo no fluxo de embed anonimo (accounting/finance), onde so ha
    # nome/email soltos vindos da URL.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    email_missing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    lgpd_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notify_on_availability: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    landing_page: Mapped["LandingPage"] = relationship(back_populates="submissions")


class AccountingAnswer(Base):
    __tablename__ = "accounting_answers"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    career_stage: Mapped[str] = mapped_column(String(100), nullable=False)
    income_method: Mapped[str] = mapped_column(String(100), nullable=False)
    accountant_status: Mapped[str] = mapped_column(String(100), nullable=False)
    revenue_range: Mapped[str] = mapped_column(String(100), nullable=False)
    willingness_to_pay: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submission: Mapped["Submission"] = relationship()


class AccountingPainSelection(Base):
    __tablename__ = "accounting_pain_selections"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), nullable=False
    )
    option: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submission: Mapped["Submission"] = relationship()


class FinanceAnswer(Base):
    __tablename__ = "finance_answers"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    career_stage: Mapped[str] = mapped_column(String(100), nullable=False)
    main_pain_point: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submission: Mapped["Submission"] = relationship()


class BenefitSelection(Base):
    __tablename__ = "benefit_selections"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), nullable=False
    )
    option: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submission: Mapped["Submission"] = relationship()


class CalculatorSelection(Base):
    __tablename__ = "calculator_selections"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.submissions.id", ondelete="CASCADE"), nullable=False
    )
    option: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submission: Mapped["Submission"] = relationship()
