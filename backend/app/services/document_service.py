"""Document intake and the processing workflow:

    upload ─▶ validate + dedupe ─▶ store ─▶ enqueue job ─▶ (worker) vision
    pipeline ─▶ evidence extraction ─▶ apply evidence ─▶ rule engine ─▶ policy

Upload returns immediately (202); the heavy CV/ML work runs in the job worker."""

import hashlib
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.extraction import extract_evidence
from app.core.config import get_settings
from app.core.errors import Conflict, InvalidInput, NotFound
from app.core.logging import log_extra
from app.core.metrics import DOCUMENTS_PROCESSED, OCR_CONFIDENCE
from app.db.models import Case, CaseStatus, Document, DocumentBlob, DocumentStatus, utcnow
from app.rule_engine.rules import RULES_BY_CODE
from app.services import adjudication_service, case_service, evidence_service, sla_service
from app.vision.loader import SUPPORTED_TYPES, UnsupportedDocument
from app.vision.pipeline import analyze_document
from app.workflow import queue

logger = logging.getLogger(__name__)
PROCESS_DOCUMENT = "process_document"


def submit(db: Session, case: Case, filename: str, content_type: str, content: bytes) -> Document:
    settings = get_settings()
    if case.status == CaseStatus.RESOLVED:
        raise Conflict("Case is resolved; documents can no longer be added")
    if content_type not in SUPPORTED_TYPES:
        raise InvalidInput("Upload a PDF, PNG, JPEG, WEBP or TIFF document")
    if not content:
        raise InvalidInput("The uploaded file is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise InvalidInput(f"Documents must be {settings.max_upload_mb} MB or smaller")

    digest = hashlib.sha256(content).hexdigest()
    duplicate = db.scalar(select(Document.id).where(Document.case_id == case.id, Document.sha256 == digest))
    if duplicate:
        raise Conflict("This document was already uploaded for this case")

    document = Document(
        case_id=case.id,
        filename=filename[:255],
        content_type=content_type,
        size_bytes=len(content),
        sha256=digest,
        status=DocumentStatus.QUEUED,
    )
    document.blob = DocumentBlob(content=content)
    db.add(document)
    db.flush()

    queue.enqueue(db, PROCESS_DOCUMENT, {"document_id": document.id})
    sla_service.fulfill_pending(db, case)
    case_service.log_event(db, case.id, "merchant", "document_uploaded", f'Document "{filename}" queued for analysis')
    return document


def get(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFound("Document not found")
    return document


def preview_jpeg(db: Session, document_id: str) -> bytes:
    preview = db.scalar(select(DocumentBlob.preview_jpeg).where(DocumentBlob.document_id == document_id))
    if not preview:
        raise NotFound("Preview not available yet")
    return preview


def process(db: Session, payload: dict[str, str]) -> None:
    """Job handler. Permanent input errors fail the document without retrying;
    anything else propagates so the queue retries with backoff."""
    document = get(db, payload["document_id"])
    case = document.case
    content = db.scalar(select(DocumentBlob.content).where(DocumentBlob.document_id == document.id))
    document.status = DocumentStatus.PROCESSING

    try:
        analysis = analyze_document(content or b"", document.content_type, get_settings().max_pdf_pages)
    except UnsupportedDocument as exc:
        mark_failed(db, document, str(exc))
        return

    extraction = extract_evidence(RULES_BY_CODE[case.reason_code], analysis, case.transaction_type)

    document.doc_type = extraction.doc_type
    document.doc_type_confidence = extraction.doc_type_confidence
    document.ocr_text = analysis.text
    document.ocr_confidence = analysis.ocr_confidence
    document.analysis = analysis.to_dict()
    document.extraction = extraction.to_dict()
    db.get_one(DocumentBlob, document.id).preview_jpeg = analysis.preview_jpeg
    document.status = DocumentStatus.COMPLETED
    document.processed_at = utcnow()

    signals = [f"{len(analysis.lines)} text lines (OCR confidence {analysis.ocr_confidence:.2f})"]
    if analysis.has_signature:
        signals.append("handwritten signature")
    if analysis.has_code:
        signals.append("machine-readable code")
    case_service.log_event(
        db,
        case.id,
        "vision",
        "document_analyzed",
        f'"{document.filename}" classified as {extraction.doc_type.replace("_", " ")} '
        f"({extraction.doc_type_confidence:.0%}); found {', '.join(signals)}",
    )
    if extraction.llm_error is None and extraction.rejected_llm_claims:
        case_service.log_event(
            db,
            case.id,
            "llm",
            "llm_claims_rejected",
            f"{len(extraction.rejected_llm_claims)} LLM claim(s) rejected: not found in the document text",
        )

    if case.transaction_type is None and extraction.transaction_type:
        case.transaction_type = extraction.transaction_type
        case_service.log_event(
            db,
            case.id,
            "ml",
            "transaction_type_inferred",
            f"Transaction type inferred from document: {extraction.transaction_type.replace('_', ' ')}",
        )

    applied = evidence_service.apply_document_evidence(db, case, document.id, extraction.accepted)
    if applied:
        adjudication_service.evaluate_case(db, case)

    DOCUMENTS_PROCESSED.labels("completed", extraction.doc_type).inc()
    OCR_CONFIDENCE.observe(analysis.ocr_confidence)
    logger.info(
        "document processed",
        extra=log_extra(
            document_id=document.id, doc_type=extraction.doc_type, evidence=applied, timings_ms=analysis.timings_ms
        ),
    )


def mark_failed(db: Session, document: Document, error: str) -> None:
    document.status = DocumentStatus.FAILED
    document.error = error
    document.processed_at = utcnow()
    DOCUMENTS_PROCESSED.labels("failed", "unknown").inc()
    case_service.log_event(
        db, document.case_id, "vision", "document_failed", f'"{document.filename}" could not be analysed: {error}'
    )


def on_exhausted(db: Session, payload: dict[str, str], error: str) -> None:
    """Called by the worker when retries are used up."""
    document = db.get(Document, payload["document_id"])
    if document is not None:
        mark_failed(db, document, "Processing failed after several attempts")
