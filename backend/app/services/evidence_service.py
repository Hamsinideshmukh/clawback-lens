"""Evidence records and the evidence dict shape the rule engine consumes."""

from sqlalchemy.orm import Session

from app.ai.extraction import EvidenceCandidate
from app.core.errors import Conflict, InvalidInput
from app.db.models import Case, CaseStatus, Evidence, EvidenceSource
from app.rule_engine.rules import RULES_BY_CODE
from app.rule_engine.schema import evidence_keys
from app.services.case_service import log_event


def evidence_dict(case: Case) -> dict[str, str | None]:
    """{evidence_key: "satisfied" | "missing", "_transactionType": ...}"""
    evidence: dict[str, str | None] = {item.key: item.status for item in case.evidence}
    evidence["_transactionType"] = case.transaction_type
    return evidence


def set_manual(db: Session, case: Case, key: str, status: str) -> Evidence:
    _ensure_editable(case)
    if key not in evidence_keys(RULES_BY_CODE[case.reason_code]):
        raise InvalidInput(f"{key!r} is not evidence for RC {case.reason_code}")

    item = _get_or_create(db, case, key)
    item.status = status
    item.source = EvidenceSource.MANUAL
    item.confidence = 1.0
    item.citation = None
    item.document_id = None
    log_event(db, case.id, "merchant", "evidence_updated", f'Evidence "{key.replace("_", " ")}" marked {status}')
    return item


def apply_document_evidence(
    db: Session, case: Case, document_id: str, candidates: list[EvidenceCandidate]
) -> list[str]:
    """Upgrades evidence to satisfied from a document. Never downgrades, and
    never overrides a merchant's manual entry or stronger earlier evidence."""
    if case.status == CaseStatus.RESOLVED:
        return []
    applied = []
    for candidate in candidates:
        item = _get_or_create(db, case, candidate.key)
        if item.status == "satisfied" and (
            item.source == EvidenceSource.MANUAL or item.confidence >= candidate.confidence
        ):
            continue
        item.status = "satisfied"
        item.source = EvidenceSource.DOCUMENT
        item.confidence = candidate.confidence
        item.citation = candidate.citation
        item.document_id = document_id
        applied.append(candidate.key)
        log_event(
            db,
            case.id,
            "+".join(candidate.sources),
            "evidence_extracted",
            f'"{candidate.key.replace("_", " ")}" extracted with confidence {candidate.confidence:.2f}: '
            f'"{candidate.citation[:160]}"',
        )
    return applied


def min_supporting_confidence(case: Case, satisfied_keys: list[str]) -> float:
    by_key = {item.key: item for item in case.evidence}
    return min((by_key[k].confidence for k in satisfied_keys if k in by_key), default=1.0)


def _get_or_create(db: Session, case: Case, key: str) -> Evidence:
    for item in case.evidence:
        if item.key == key:
            return item
    item = Evidence(case_id=case.id, key=key, status="missing")
    case.evidence.append(item)
    db.add(item)
    return item


def _ensure_editable(case: Case) -> None:
    if case.status == CaseStatus.RESOLVED:
        raise Conflict("Case is resolved; evidence can no longer change")
