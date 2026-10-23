"""Runs the rule engine for a case, records the verdict, and applies the
lifecycle policy. This is the single path to a verdict in the system: the API,
the document worker and the copilot all come through here."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Conflict
from app.core.metrics import VERDICTS
from app.db.models import Case, CaseStatus, Outcome, RuleEvaluation
from app.rule_engine.evaluate import evaluate
from app.rule_engine.explain import explain
from app.rule_engine.models import Verdict
from app.rule_engine.rules import RULES_BY_CODE
from app.services import case_service, evidence_service
from app.workflow import policy


def preview(case: Case) -> tuple[Verdict, str]:
    """Evaluates without persisting anything (used by the copilot)."""
    verdict = evaluate(RULES_BY_CODE[case.reason_code], evidence_service.evidence_dict(case))
    return verdict, explain(verdict)


def evaluate_case(db: Session, case: Case, actor: str = "rule_engine") -> RuleEvaluation:
    verdict, explanation = preview(case)
    record = RuleEvaluation(
        case_id=case.id,
        reason_code=verdict.reason_code,
        status=verdict.status,
        satisfied=verdict.satisfied,
        missing=verdict.missing,
        contestability=verdict.contestability,
        explanation=explanation,
    )
    case.evaluations.append(record)
    db.add(record)
    VERDICTS.labels(verdict.status).inc()
    case_service.log_event(db, case.id, actor, "verdict_issued", f"Verdict: {verdict.status} — {explanation}")

    transition = policy.after_evaluation(
        current=CaseStatus(case.status),
        verdict=verdict.status,
        min_supporting_confidence=evidence_service.min_supporting_confidence(case, verdict.satisfied),
        auto_resolve_min_confidence=get_settings().auto_resolve_min_confidence,
    )
    if transition:
        case_service.apply_transition(db, case, transition, "workflow")
    return record


def decide(db: Session, case: Case, outcome: Outcome, note: str | None) -> None:
    try:
        transition = policy.after_analyst_decision(CaseStatus(case.status), outcome)
    except ValueError as exc:
        raise Conflict(str(exc)) from exc
    if note:
        transition = policy.Transition(transition.status, transition.outcome, f"Analyst decision: {note}")
    case_service.apply_transition(db, case, transition, "analyst")
