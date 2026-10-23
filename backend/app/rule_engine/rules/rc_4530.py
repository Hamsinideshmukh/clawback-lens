"""Reason Code 4530 — Currency Discrepancy."""

from app.rule_engine.models import Rule

rule_4530 = Rule(
    reason_code="4530",
    name="Currency Discrepancy",
    max_days_to_raise=120,
    max_days_to_challenge=20,
    requirement={
        "type": "one_of",
        "options": ["correcting_transaction_processed", "chargeback_raised_in_error"],
    },
)
