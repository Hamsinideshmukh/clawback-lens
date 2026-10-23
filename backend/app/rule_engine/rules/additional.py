"""Additional card-network chargeback rules.

Each checklist follows the guide's "one of the following" requirements to
challenge a dispute.  The descriptions are our structured representations,
not verbatim guide text.
"""

from app.rule_engine.models import Rule


def _one_of(reason_code: str, name: str, options: list[str]) -> Rule:
    return Rule(
        reason_code=reason_code,
        name=name,
        max_days_to_raise=120,
        max_days_to_challenge=20,
        requirement={"type": "one_of", "options": options},
    )


rule_4512 = _one_of(
    "4512",
    "Multiple Processing",
    [
        "correcting_transaction_processed",
        "transactions_linked_to_card_member",
        "chargeback_raised_in_error",
    ],
)
rule_4513 = _one_of(
    "4513",
    "Credit Not Presented",
    [
        "correcting_transaction_processed",
        "substitute_goods_accepted",
        "return_claim_refuted",
        "cancellation_policy_provided",
        "chargeback_raised_in_error",
    ],
)
rule_4515 = _one_of(
    "4515",
    "Paid Through Other Means",
    [
        "correcting_transaction_processed",
        "other_payment_unrelated",
        "chargeback_raised_in_error",
    ],
)
rule_4521 = _one_of(
    "4521",
    "Invalid Authorisation",
    [
        "correcting_transaction_processed",
        "valid_authorisation_proof",
        "authorisation_within_seven_days",
        "chargeback_raised_in_error",
    ],
)
rule_4536 = _one_of(
    "4536",
    "Late Presentment",
    [
        "correcting_transaction_processed",
        "presentment_within_timeframe",
        "chargeback_raised_in_error",
    ],
)
rule_4540 = _one_of(
    "4540",
    "Card Not Present",
    [
        "correcting_transaction_processed",
        "signed_carrier_delivery_receipt",
        "chargeback_raised_in_error",
    ],
)
rule_4544 = _one_of(
    "4544",
    "Cancellation Of Recurring Goods / Services",
    [
        "correcting_transaction_processed",
        "chargeback_raised_in_error",
    ],
)
rule_4516 = _one_of(
    "4516",
    "Request For Support Not Fulfilled",
    [
        "correcting_transaction_processed",
        "chargeback_raised_in_error",
    ],
)
rule_4755 = _one_of(
    "4755",
    "No Valid Authorisation",
    [
        "correcting_transaction_processed",
        "valid_authorisation_proof",
        "transaction_within_card_validity",
        "chargeback_raised_in_error",
    ],
)
