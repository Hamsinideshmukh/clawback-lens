import pytest

from app.db.models import CaseStatus, Outcome
from app.workflow import policy

THRESHOLD = 0.8


def test_trusted_evidence_auto_resolves_for_merchant() -> None:
    t = policy.after_evaluation(CaseStatus.OPEN, "auto_resolve_merchant", 0.95, THRESHOLD)
    assert t is not None
    assert (t.status, t.outcome) == (CaseStatus.RESOLVED, Outcome.MERCHANT)


def test_low_confidence_model_evidence_routes_to_a_human() -> None:
    t = policy.after_evaluation(CaseStatus.OPEN, "auto_resolve_merchant", 0.6, THRESHOLD)
    assert t is not None
    assert t.status == CaseStatus.ESCALATED
    assert "0.60" in t.reason


def test_judgment_heavy_verdict_escalates() -> None:
    t = policy.after_evaluation(CaseStatus.OPEN, "escalate_to_human", 1.0, THRESHOLD)
    assert t is not None
    assert t.status == CaseStatus.ESCALATED


@pytest.mark.parametrize("verdict", ["insufficient_evidence", "auto_resolve_card_member"])
def test_insufficient_evidence_keeps_case_open(verdict: str) -> None:
    assert policy.after_evaluation(CaseStatus.OPEN, verdict, 1.0, THRESHOLD) is None  # type: ignore[arg-type]


def test_withdrawn_evidence_reopens_an_escalated_case() -> None:
    t = policy.after_evaluation(CaseStatus.ESCALATED, "insufficient_evidence", 1.0, THRESHOLD)
    assert t is not None
    assert t.status == CaseStatus.OPEN


def test_resolved_cases_are_final() -> None:
    assert policy.after_evaluation(CaseStatus.RESOLVED, "escalate_to_human", 1.0, THRESHOLD) is None
    assert policy.after_deadline(CaseStatus.RESOLVED) is None
    with pytest.raises(ValueError, match="already resolved"):
        policy.after_analyst_decision(CaseStatus.RESOLVED, Outcome.MERCHANT)


def test_deadline_resolves_open_cases_for_card_member() -> None:
    t = policy.after_deadline(CaseStatus.OPEN)
    assert t is not None
    assert (t.status, t.outcome) == (CaseStatus.RESOLVED, Outcome.CARD_MEMBER)
    assert policy.after_deadline(CaseStatus.ESCALATED) is None


@pytest.mark.parametrize(
    "url",
    ["postgres://u:p@host:5432/db", "postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"],
)
def test_database_url_is_normalised_to_psycopg(url: str) -> None:
    from app.core.config import Settings

    assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@host:5432/db"
