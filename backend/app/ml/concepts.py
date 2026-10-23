"""Evidence concepts predicted by the ML model, mapped to rule-engine keys.

Some reason codes use different keys for the same real-world evidence
(RC 4554 "signed_delivery_receipt" vs RC 4540 "signed_carrier_delivery_receipt").
The classifier predicts the concept; this module resolves it to whichever
key the case's rule actually uses."""

CONCEPT_KEYS: dict[str, list[str]] = {
    "signed_delivery": ["signed_delivery_receipt", "signed_carrier_delivery_receipt"],
    "return_refuted": ["return_refuted_proof", "return_claim_refuted"],
}

_KEY_TO_CONCEPT = {key: concept for concept, keys in CONCEPT_KEYS.items() for key in keys}


def concept_for_key(key: str) -> str:
    return _KEY_TO_CONCEPT.get(key, key)


def keys_for_concept(concept: str, rule_keys: list[str]) -> list[str]:
    """Rule keys (of the given rule) that a predicted concept satisfies."""
    return [key for key in CONCEPT_KEYS.get(concept, [concept]) if key in rule_keys]


# Transaction type implied by a document type, used to pick the branch of
# branch_by_transaction_type rules (RC 4554) when the case does not set one.
DOC_TYPE_TRANSACTION: dict[str, str] = {
    "delivery_receipt": "physical_goods",
    "boarding_pass": "travel",
    "digital_access_log": "digital_goods",
}
