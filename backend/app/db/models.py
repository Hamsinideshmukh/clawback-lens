"""Relational schema. Statuses are stored as plain strings backed by StrEnums
so new states never require a Postgres enum migration."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class CaseStatus(StrEnum):
    OPEN = "open"  # accepting merchant evidence
    ESCALATED = "escalated"  # waiting on a human analyst
    RESOLVED = "resolved"


class Outcome(StrEnum):
    MERCHANT = "merchant"
    CARD_MEMBER = "card_member"


class EvidenceSource(StrEnum):
    MANUAL = "manual"
    DOCUMENT = "document"


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(String(64), index=True)
    merchant_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    reason_code: Mapped[str] = mapped_column(String(8))
    transaction_type: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=CaseStatus.OPEN, index=True)
    outcome: Mapped[str | None] = mapped_column(String(16))
    respond_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    retrieval_requests: Mapped[list["RetrievalRequest"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    evaluations: Mapped[list["RuleEvaluation"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="RuleEvaluation.evaluated_at"
    )
    events: Mapped[list["TimelineEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="TimelineEvent.occurred_at"
    )


class Evidence(Base):
    """One rule-engine evidence key per case. Document-derived evidence keeps
    a verbatim citation and model confidence so every claim is auditable."""

    __tablename__ = "evidence"
    __table_args__ = (UniqueConstraint("case_id", "key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # satisfied | missing
    source: Mapped[str] = mapped_column(String(16), default=EvidenceSource.MANUAL)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    citation: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    case: Mapped[Case] = relationship(back_populates="evidence")


class Document(Base):
    """An uploaded evidence file and everything the vision pipeline learned about it."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=DocumentStatus.QUEUED)
    doc_type: Mapped[str | None] = mapped_column(String(32))
    doc_type_confidence: Mapped[float | None] = mapped_column(Float)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # pages, regions, quality, timings
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # evidence candidates + provenance
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    case: Mapped[Case] = relationship(back_populates="documents")
    blob: Mapped["DocumentBlob"] = relationship(cascade="all, delete-orphan", uselist=False, lazy="raise")


class DocumentBlob(Base):
    """Raw bytes kept apart from metadata so listing documents never loads files.
    Postgres keeps the deployment to a single stateful dependency; swap for
    object storage by replacing services/document_service.py storage calls."""

    __tablename__ = "document_blobs"

    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    preview_jpeg: Mapped[bytes | None] = mapped_column(LargeBinary)


class RetrievalRequest(Base):
    __tablename__ = "retrieval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    reason_code: Mapped[str] = mapped_column(String(8), default="6014")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | fulfilled | unfulfilled

    case: Mapped[Case] = relationship(back_populates="retrieval_requests")


class RuleEvaluation(Base):
    __tablename__ = "rule_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    reason_code: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(32))
    satisfied: Mapped[list[str]] = mapped_column(JSONB, default=list)
    missing: Mapped[list[str]] = mapped_column(JSONB, default=list)
    contestability: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="evaluations")


class TimelineEvent(Base):
    """Append-only audit log; every state change writes one row."""

    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    actor: Mapped[str] = mapped_column(String(32))  # system | merchant | analyst | vision | ml | llm | rule_engine
    event_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[Case] = relationship(back_populates="events")


class Job(Base):
    """Durable work queue. Workers claim rows with FOR UPDATE SKIP LOCKED, so
    any number of worker processes can run without double-processing."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claimable", "run_after", postgresql_where=text("status = 'queued'")),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
