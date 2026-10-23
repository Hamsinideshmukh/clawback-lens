"""Case lifecycle policy: a pure function from (current state, verdict,
evidence trust) to the next state. Kept free of I/O so every transition is
covered by fast unit tests.

    open ──verdict: merchant wins, evidence trusted──────────▶ resolved (merchant)
      │  ──verdict: merchant wins, model evidence < threshold─▶ escalated
      │  ──verdict: judgment-heavy reason code───────────────▶ escalated
      │  ──response deadline passes──────────────────────────▶ resolved (card member)
    escalated ──analyst decision─────────────────────────────▶ resolved
"""

from dataclasses import dataclass

from app.db.models import CaseStatus, Outcome
from app.rule_engine.models import VerdictStatus


@dataclass(frozen=True)
class Transition:
    status: CaseStatus
    outcome: Outcome | None
    reason: str


def after_evaluation(
    current: CaseStatus,
    verdict: VerdictStatus,
    min_supporting_confidence: float,
    auto_resolve_min_confidence: float,
) -> Transition | None:
    """Returns the transition to apply, or None to stay put."""
    if current == CaseStatus.RESOLVED:
        return None

    if verdict == "escalate_to_human":
        target = Transition(CaseStatus.ESCALATED, None, "Reason code requires human judgment")
    elif verdict == "auto_resolve_merchant":
        if min_supporting_confidence >= auto_resolve_min_confidence:
            target = Transition(CaseStatus.RESOLVED, Outcome.MERCHANT, "Required evidence satisfied")
        else:
            target = Transition(
                CaseStatus.ESCALATED,
                None,
                f"Evidence satisfies the rule but model confidence {min_supporting_confidence:.2f} "
                f"is below {auto_resolve_min_confidence:.2f}; human review required",
            )
    else:
        # Insufficient evidence: the merchant may still respond until the deadline.
        target = Transition(CaseStatus.OPEN, None, "Awaiting further evidence")

    return None if target.status == current and target.outcome is None else target


def after_deadline(current: CaseStatus) -> Transition | None:
    if current != CaseStatus.OPEN:
        return None
    return Transition(
        CaseStatus.RESOLVED, Outcome.CARD_MEMBER, "Merchant response window closed without sufficient evidence"
    )


def after_analyst_decision(current: CaseStatus, outcome: Outcome) -> Transition:
    if current == CaseStatus.RESOLVED:
        raise ValueError("Case is already resolved")
    return Transition(CaseStatus.RESOLVED, outcome, "Analyst decision")
