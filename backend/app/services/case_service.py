"""Case domain: creation, lookup, lifecycle transitions and the audit timeline.
Services never commit; the API request or worker job owns the transaction."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import InvalidInput, NotFound
from app.db.models import Case, CaseStatus, TimelineEvent, utcnow
from app.rule_engine.rules import RULES_BY_CODE
from app.rule_engine.schema import transaction_types
from app.schemas.case import CaseCreate
from app.workflow.policy import Transition


def create_case(db: Session, data: CaseCreate) -> Case:
    rule = RULES_BY_CODE.get(data.reason_code)
    if rule is None:
        raise InvalidInput(f"Unsupported reason code {data.reason_code}")
    if data.transaction_type and data.transaction_type not in transaction_types(rule):
        raise InvalidInput(f"RC {data.reason_code} does not use transaction type {data.transaction_type!r}")

    case = Case(
        transaction_id=data.transaction_id,
        merchant_name=data.merchant_name,
        amount=data.amount,
        currency=data.currency,
        reason_code=data.reason_code,
        transaction_type=data.transaction_type,
        status=CaseStatus.OPEN,
        respond_by=utcnow() + timedelta(days=get_settings().case_response_days),
    )
    db.add(case)
    db.flush()
    log_event(db, case.id, "system", "case_opened", f"Dispute opened under RC {rule.reason_code} ({rule.name})")
    return case


def get_case(db: Session, case_id: str) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise NotFound("Case not found")
    return case


def list_cases(db: Session, status: CaseStatus | None, limit: int, offset: int) -> tuple[list[Case], int]:
    query = select(Case)
    if status:
        query = query.where(Case.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    cases = db.scalars(query.order_by(Case.created_at.desc()).limit(limit).offset(offset)).all()
    return list(cases), total


def status_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(Case.status, func.count()).group_by(Case.status)).all()
    return dict(rows)


def apply_transition(db: Session, case: Case, transition: Transition, actor: str) -> None:
    case.status = transition.status
    case.outcome = transition.outcome
    outcome = f" in favour of the {transition.outcome.replace('_', ' ')}" if transition.outcome else ""
    log_event(
        db, case.id, actor, f"case_{transition.status}", f"Case {transition.status}{outcome}: {transition.reason}"
    )


def log_event(db: Session, case_id: str, actor: str, event_type: str, description: str) -> TimelineEvent:
    event = TimelineEvent(case_id=case_id, actor=actor, event_type=event_type, description=description)
    db.add(event)
    return event
