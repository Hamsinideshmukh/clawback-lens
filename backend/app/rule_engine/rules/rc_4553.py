"""Reason Code 4553 — Not As Described Or Defective Merchandise.
Judgment-heavy: always_escalate=True means even a fully-satisfied
checklist still routes to a human. The engine assembles evidence;
it never rubber-stamps this one."""

from app.rule_engine.models import Rule

rule_4553 = Rule(
    reason_code="4553",
    name="Not As Described Or Defective Merchandise",
    max_days_to_raise=120,
    max_days_to_challenge=20,
    always_escalate=True,
    requirement={
        "type": "n_of_m",
        "n": 1,
        "options": ["return_refuted_proof", "description_match_proof", "repair_or_replacement_offered"],
    },
)
