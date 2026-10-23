"""Request and response bodies for the HTTP API."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import CaseStatus, DocumentStatus, Outcome


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CaseCreate(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=64)
    merchant_name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    reason_code: str
    transaction_type: str | None = None


class EvidenceOut(ORM):
    key: str
    status: str
    source: str
    confidence: float
    citation: str | None
    document_id: str | None
    submitted_at: datetime


class EvidenceUpdate(BaseModel):
    status: Literal["satisfied", "missing"]


class EvaluationOut(ORM):
    reason_code: str
    status: str
    satisfied: list[str]
    missing: list[str]
    contestability: str | None
    explanation: str
    evaluated_at: datetime


class DocumentOut(ORM):
    id: str
    case_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    doc_type: str | None
    doc_type_confidence: float | None
    ocr_confidence: float | None
    error: str | None
    created_at: datetime
    processed_at: datetime | None


class DocumentDetail(DocumentOut):
    ocr_text: str | None
    analysis: dict[str, Any] | None
    extraction: dict[str, Any] | None


class RetrievalRequestOut(ORM):
    id: str
    reason_code: str
    issued_at: datetime
    deadline: datetime
    status: str


class CaseSummary(ORM):
    id: str
    transaction_id: str
    merchant_name: str
    amount: Decimal
    currency: str
    reason_code: str
    transaction_type: str | None
    status: CaseStatus
    outcome: Outcome | None
    respond_by: datetime
    created_at: datetime


class CaseDetail(CaseSummary):
    reason_name: str
    required_evidence: list[str]
    evidence: list[EvidenceOut]
    documents: list[DocumentOut]
    retrieval_requests: list[RetrievalRequestOut]
    latest_evaluation: EvaluationOut | None


class CaseList(BaseModel):
    items: list[CaseSummary]
    total: int
    status_counts: dict[str, int]


class DecisionIn(BaseModel):
    outcome: Outcome
    note: str | None = Field(default=None, max_length=1000)


class TimelineEventOut(ORM):
    actor: str
    event_type: str
    description: str
    occurred_at: datetime


class ReasonCodeOut(BaseModel):
    reason_code: str
    name: str
    always_escalate: bool
    transaction_types: list[str]
    evidence: dict[str, str]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str]
    mode: Literal["llm", "deterministic"]
