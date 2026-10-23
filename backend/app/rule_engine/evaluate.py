"""The Deterministic Rule Engine: the ONLY component authorised to produce a
verdict. `evaluate()` is a pure function — same rule and evidence always give
the same output, with no database, network, or model involved. Vision, ML and
LLM components may only *propose* evidence; they never decide."""

from typing import Any

from app.rule_engine.models import Rule, Verdict, VerdictStatus

Evidence = dict[str, str | None]


def _evaluate_requirement(requirement: dict[str, Any], evidence: Evidence) -> dict[str, Any]:
    """Recursively evaluates a requirement tree.
    Returns {"met": bool, "satisfied": [...], "missing": [...]}."""
    req_type = requirement["type"]

    if req_type in ("one_of", "n_of_m"):
        needed = 1 if req_type == "one_of" else requirement["n"]
        options = requirement["options"]
        satisfied = [o for o in options if evidence.get(o) == "satisfied"]
        missing = [o for o in options if evidence.get(o) != "satisfied"]
        return {"met": len(satisfied) >= needed, "satisfied": satisfied, "missing": missing}

    if req_type == "branch_by_transaction_type":
        branch = requirement.get(evidence.get("_transactionType") or "")
        if branch is None:
            # Unknown transaction type: report it as missing instead of raising,
            # so callers get a clean "insufficient_evidence" verdict.
            return {"met": False, "satisfied": [], "missing": ["_transactionType"]}
        return _evaluate_requirement(branch, evidence)

    raise ValueError(f"Unknown requirement type: {req_type}")


def evaluate(rule: Rule, evidence: Evidence) -> Verdict:
    """
    :param rule: a Rule from app.rule_engine.rules
    :param evidence: evidence key -> "satisfied" | "missing", plus optionally
        "_transactionType" for branching rules.
    """
    result = _evaluate_requirement(rule.requirement, evidence)

    status: VerdictStatus
    if rule.always_escalate:
        status = "escalate_to_human"
    elif result["met"]:
        status = "auto_resolve_merchant"
    elif not result["satisfied"]:
        status = "auto_resolve_card_member"
    else:
        status = "insufficient_evidence"

    contestability = None
    if result["missing"] and not result["met"]:
        item = result["missing"][0].lstrip("_").replace("_", " ")
        contestability = f'Providing "{item}" would change this outcome.'

    return Verdict(
        reason_code=rule.reason_code,
        reason_name=rule.name,
        status=status,
        satisfied=result["satisfied"],
        missing=result["missing"],
        contestability=contestability,
    )
