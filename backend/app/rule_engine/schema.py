"""Introspects a Rule's requirement tree: which evidence keys does it care
about, and what do they mean? The rule structure drives what the ML and LLM
extractors look for, so there is no separate list that can drift out of sync."""

from app.rule_engine.models import Rule

EVIDENCE_DESCRIPTIONS: dict[str, str] = {
    "correcting_transaction_processed": "A correcting/offsetting transaction or refund has already been processed",
    "chargeback_raised_in_error": "Evidence that the chargeback itself was raised in error",
    "signed_delivery_receipt": "A signed delivery receipt confirming the card member received the goods",
    "delivery_address_match": "Proof the delivery address matches the address the card member specified",
    "ip_address_match": "The IP address used matches a previous undisputed transaction",
    "email_delivery_match": "The email used for delivery matches the card member's known email",
    "post_purchase_access_log": "Evidence the card member accessed/downloaded the digital goods after purchase",
    "boarding_pass_scan": "A scanned boarding pass or passenger manifest showing travel occurred",
    "loyalty_point_credit_proof": "Frequent flyer / loyalty point credit tied to this specific trip",
    "return_refuted_proof": "Evidence refuting the card member's claim that goods were returned",
    "description_match_proof": "Evidence the goods matched the merchant's written description",
    "repair_or_replacement_offered": "Evidence the merchant offered a repair or replacement for defective goods",
    "transactions_linked_to_card_member": "Itemised records linking each submitted transaction to the card member",
    "substitute_goods_accepted": "Proof the card member accepted substitute goods or services instead of a credit",
    "return_claim_refuted": "Proof refuting the card member's claim that goods were returned",
    "cancellation_policy_provided": "Proof the cancellation policy was provided at purchase and not followed",
    "other_payment_unrelated": "Proof an alternative payment was not related to the disputed transaction",
    "valid_authorisation_proof": "Proof of a valid authorisation for the disputed transaction",
    "authorisation_within_seven_days": "Proof the charge was received within seven days of authorisation",
    "presentment_within_timeframe": "Proof the charge was submitted within the required timeframe",
    "signed_carrier_delivery_receipt": "Signed carrier delivery receipt for the goods",
    "transaction_within_card_validity": "Proof the transaction date fell within the card's valid date range",
}


def evidence_keys(rule: Rule) -> list[str]:
    """Every evidence key any branch of the rule can use, in stable order."""
    req = rule.requirement
    if req["type"] in ("one_of", "n_of_m"):
        return list(req["options"])
    keys: list[str] = []
    for branch in transaction_types(rule):
        keys.extend(k for k in req[branch]["options"] if k not in keys)
    return keys


def transaction_types(rule: Rule) -> list[str]:
    """Branch names for branch_by_transaction_type rules, else an empty list."""
    req = rule.requirement
    if req["type"] != "branch_by_transaction_type":
        return []
    return [k for k in req if k != "type"]


def keys_for_branch(rule: Rule, transaction_type: str | None) -> list[str]:
    if transaction_type and transaction_type in transaction_types(rule):
        return list(rule.requirement[transaction_type]["options"])
    return evidence_keys(rule)
