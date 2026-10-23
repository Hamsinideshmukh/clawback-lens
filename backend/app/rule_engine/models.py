"""Typed structures for the Rule Engine. Plain dataclasses with no framework
dependency: the engine is importable and testable in total isolation from
FastAPI, SQLAlchemy, the vision pipeline, or any model."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

VerdictStatus = Literal[
    "auto_resolve_merchant",
    "auto_resolve_card_member",
    "insufficient_evidence",
    "escalate_to_human",
]


@dataclass(frozen=True)
class Rule:
    reason_code: str
    name: str
    requirement: dict[str, Any]
    max_days_to_raise: int = 120
    max_days_to_challenge: int = 20
    always_escalate: bool = False


@dataclass(frozen=True)
class Verdict:
    reason_code: str
    reason_name: str
    status: VerdictStatus
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    contestability: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


STATUS_LABELS: dict[str, str] = {
    "auto_resolve_merchant": "Resolved — Merchant",
    "auto_resolve_card_member": "Resolved — Card Member",
    "insufficient_evidence": "Insufficient Evidence",
    "escalate_to_human": "Needs Human Review",
}
