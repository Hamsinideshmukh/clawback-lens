from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.agents.supervisor import handle_chat
from app.api.deps import copilot_limit
from app.db.models import Case, CaseStatus
from app.db.session import get_db
from app.rule_engine.rules import RULES_BY_CODE
from app.rule_engine.schema import keys_for_branch
from app.schemas.case import (
    CaseCreate,
    CaseDetail,
    CaseList,
    CaseSummary,
    ChatRequest,
    ChatResponse,
    DecisionIn,
    DocumentOut,
    EvaluationOut,
    EvidenceOut,
    EvidenceUpdate,
    RetrievalRequestOut,
    TimelineEventOut,
)
from app.services import adjudication_service, case_service, evidence_service, sla_service

router = APIRouter(prefix="/cases", tags=["cases"])


def _detail(case: Case) -> CaseDetail:
    rule = RULES_BY_CODE[case.reason_code]
    latest = case.evaluations[-1] if case.evaluations else None
    return CaseDetail(
        **CaseSummary.model_validate(case).model_dump(),
        reason_name=rule.name,
        required_evidence=keys_for_branch(rule, case.transaction_type),
        evidence=[EvidenceOut.model_validate(e) for e in case.evidence],
        documents=[DocumentOut.model_validate(d) for d in sorted(case.documents, key=lambda d: d.created_at)],
        retrieval_requests=[RetrievalRequestOut.model_validate(r) for r in case.retrieval_requests],
        latest_evaluation=EvaluationOut.model_validate(latest) if latest else None,
    )


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> CaseDetail:
    case = case_service.create_case(db, payload)
    db.commit()
    return _detail(case)


@router.get("", response_model=CaseList)
def list_cases(
    status_filter: CaseStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CaseList:
    cases, total = case_service.list_cases(db, status_filter, limit, offset)
    return CaseList.model_validate(
        {"items": cases, "total": total, "status_counts": case_service.status_counts(db)}, from_attributes=True
    )


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseDetail:
    return _detail(case_service.get_case(db, case_id))


@router.put("/{case_id}/evidence/{key}", response_model=CaseDetail)
def update_evidence(case_id: str, key: str, payload: EvidenceUpdate, db: Session = Depends(get_db)) -> CaseDetail:
    case = case_service.get_case(db, case_id)
    evidence_service.set_manual(db, case, key, payload.status)
    adjudication_service.evaluate_case(db, case)
    db.commit()
    return _detail(case)


@router.post("/{case_id}/evaluate", response_model=EvaluationOut)
def evaluate_case(case_id: str, db: Session = Depends(get_db)) -> EvaluationOut:
    case = case_service.get_case(db, case_id)
    record = adjudication_service.evaluate_case(db, case)
    db.commit()
    return EvaluationOut.model_validate(record)


@router.post("/{case_id}/decision", response_model=CaseDetail)
def decide(case_id: str, payload: DecisionIn, db: Session = Depends(get_db)) -> CaseDetail:
    case = case_service.get_case(db, case_id)
    adjudication_service.decide(db, case, payload.outcome, payload.note)
    db.commit()
    return _detail(case)


@router.post("/{case_id}/retrieval-requests", response_model=RetrievalRequestOut, status_code=201)
def create_retrieval_request(case_id: str, db: Session = Depends(get_db)) -> RetrievalRequestOut:
    case = case_service.get_case(db, case_id)
    request = sla_service.create_retrieval_request(db, case)
    db.commit()
    return RetrievalRequestOut.model_validate(request)


@router.get("/{case_id}/timeline", response_model=list[TimelineEventOut])
def get_timeline(case_id: str, db: Session = Depends(get_db)) -> list[TimelineEventOut]:
    case = case_service.get_case(db, case_id)
    return [TimelineEventOut.model_validate(e) for e in case.events]


@router.post("/{case_id}/copilot", response_model=ChatResponse, dependencies=[Depends(copilot_limit)])
def copilot(case_id: str, payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return handle_chat(case_service.get_case(db, case_id), payload.message)
