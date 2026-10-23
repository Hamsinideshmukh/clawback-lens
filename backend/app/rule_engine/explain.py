"""
app/rule_engine/explain.py

Converts a structured Verdict into a human-readable explanation.
This is deterministic template logic, not an LLM call — the
underlying reasoning always originates from the Rule Engine itself.
An AI layer may later rephrase this more conversationally, but it
must never change the substance of what's being explained.
"""

from app.rule_engine.models import STATUS_LABELS, Verdict


def explain(verdict: Verdict) -> str:
    label = STATUS_LABELS[verdict.status]

    if verdict.status == "escalate_to_human":
        return (
            f"Reason Code {verdict.reason_code} ({verdict.reason_name}) is judgment-heavy "
            f"and always routes to a human reviewer, regardless of evidence completeness. "
            f"Satisfied items: {', '.join(verdict.satisfied) or 'none'}."
        )

    if verdict.status == "auto_resolve_merchant":
        return (
            f"Reason Code {verdict.reason_code} ({verdict.reason_name}) resolved in the "
            f"merchant's favor. Requirement satisfied by: {', '.join(verdict.satisfied)}."
        )

    if verdict.status == "auto_resolve_card_member":
        return (
            f"Reason Code {verdict.reason_code} ({verdict.reason_name}) currently favours the "
            f"card member: the merchant has provided no qualifying evidence. {verdict.contestability or ''}"
        ).strip()

    # insufficient_evidence
    missing_str = ", ".join(verdict.missing) if verdict.missing else "additional evidence"
    return (
        f"Reason Code {verdict.reason_code} ({verdict.reason_name}) is currently "
        f"{label.lower()}. Missing: {missing_str}. "
        f"{verdict.contestability or ''}"
    ).strip()
