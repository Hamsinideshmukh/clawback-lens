"""The deadline / SLA engine. Knows nothing about evidence quality, only time:

* Retrieval Requests (pre-dispute requests for information, RC 6014) that pass
  their deadline unanswered escalate the case to RC 4516, "Request For Support
  Not Fulfilled".
* Open cases whose merchant response window closes are resolved in the card
  member's favour.

`sweep()` takes `now` as a parameter so tests can move time without waiting;
the worker runs it periodically against the real clock."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Case, CaseStatus, RetrievalRequest, utcnow
from app.services import adjudication_service, case_service
from app.workflow import policy

RC_REQUEST_NOT_FULFILLED = "4516"


def create_retrieval_request(db: Session, case: Case, reason_code: str = "6014") -> RetrievalRequest:
    request = RetrievalRequest(
        case_id=case.id,
        reason_code=reason_code,
        deadline=utcnow() + timedelta(days=get_settings().retrieval_sla_days),
    )
    db.add(request)
    case.retrieval_requests.append(request)
    case_service.log_event(
        db,
        case.id,
        "system",
        "retrieval_request_issued",
        f"Retrieval Request issued (RC {reason_code}); merchant must respond by {request.deadline:%Y-%m-%d %H:%M} UTC",
    )
    return request


def fulfill_pending(db: Session, case: Case) -> None:
    """A merchant submission answers any open Retrieval Request."""
    for request in case.retrieval_requests:
        if request.status == "pending":
            request.status = "fulfilled"
            case_service.log_event(
                db, case.id, "merchant", "retrieval_request_fulfilled", "Merchant responded within the SLA window"
            )


def sweep(db: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    breached = db.scalars(
        select(RetrievalRequest)
        .where(RetrievalRequest.status == "pending", RetrievalRequest.deadline <= now)
        .with_for_update(skip_locked=True)
    ).all()
    for request in breached:
        request.status = "unfulfilled"
        case = request.case
        case.reason_code = RC_REQUEST_NOT_FULFILLED
        case_service.log_event(
            db,
            case.id,
            "sla_engine",
            "auto_escalated_to_chargeback",
            "Retrieval Request deadline missed; escalated to chargeback under RC 4516 "
            "(Request For Support Not Fulfilled)",
        )

    expired = db.scalars(
        select(Case).where(Case.status == CaseStatus.OPEN, Case.respond_by <= now).with_for_update(skip_locked=True)
    ).all()
    for case in expired:
        adjudication_service.evaluate_case(db, case, actor="sla_engine")
        if case.status == CaseStatus.OPEN:  # evidence still insufficient at the deadline
            transition = policy.after_deadline(CaseStatus.OPEN)
            if transition:
                case_service.apply_transition(db, case, transition, "sla_engine")

    return {"retrieval_requests_breached": len(breached), "cases_expired": len(expired)}
