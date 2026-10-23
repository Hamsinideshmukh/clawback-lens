"""The rule engine is a pure function: these tests need no database or models."""

import pytest

from app.rule_engine.evaluate import evaluate
from app.rule_engine.explain import explain
from app.rule_engine.rules import RULES_BY_CODE
from app.rule_engine.schema import evidence_keys, keys_for_branch, transaction_types


def test_one_of_rule_resolves_for_merchant_when_any_option_satisfied() -> None:
    verdict = evaluate(RULES_BY_CODE["4530"], {"correcting_transaction_processed": "satisfied"})
    assert verdict.status == "auto_resolve_merchant"
    assert verdict.satisfied == ["correcting_transaction_processed"]
    assert verdict.contestability is None


def test_no_evidence_resolves_for_card_member() -> None:
    verdict = evaluate(RULES_BY_CODE["4530"], {})
    assert verdict.status == "auto_resolve_card_member"
    assert verdict.contestability == 'Providing "correcting transaction processed" would change this outcome.'


@pytest.mark.parametrize(
    ("transaction_type", "evidence", "expected"),
    [
        ("physical_goods", {"signed_delivery_receipt": "satisfied"}, "auto_resolve_merchant"),
        ("physical_goods", {"ip_address_match": "satisfied"}, "auto_resolve_card_member"),
        ("digital_goods", {"ip_address_match": "satisfied"}, "auto_resolve_merchant"),
        ("travel", {"boarding_pass_scan": "satisfied"}, "auto_resolve_merchant"),
    ],
)
def test_branching_rule_only_counts_evidence_for_the_transaction_type(
    transaction_type: str, evidence: dict[str, str], expected: str
) -> None:
    verdict = evaluate(RULES_BY_CODE["4554"], {"_transactionType": transaction_type, **evidence})
    assert verdict.status == expected


def test_branching_rule_without_transaction_type_is_insufficient_not_an_error() -> None:
    verdict = evaluate(RULES_BY_CODE["4554"], {"signed_delivery_receipt": "satisfied"})
    assert verdict.status == "auto_resolve_card_member"
    assert verdict.missing == ["_transactionType"]


def test_judgment_heavy_rule_always_escalates_even_with_complete_evidence() -> None:
    rule = RULES_BY_CODE["4553"]
    verdict = evaluate(rule, dict.fromkeys(evidence_keys(rule), "satisfied"))
    assert verdict.status == "escalate_to_human"
    assert "human reviewer" in explain(verdict)


def test_evaluate_is_deterministic() -> None:
    evidence = {"_transactionType": "digital_goods", "email_delivery_match": "satisfied"}
    assert evaluate(RULES_BY_CODE["4554"], evidence) == evaluate(RULES_BY_CODE["4554"], evidence)


def test_schema_helpers() -> None:
    rule = RULES_BY_CODE["4554"]
    assert transaction_types(rule) == ["physical_goods", "digital_goods", "travel"]
    assert keys_for_branch(rule, "travel") == ["boarding_pass_scan", "loyalty_point_credit_proof"]
    assert keys_for_branch(rule, None) == evidence_keys(rule)
    assert transaction_types(RULES_BY_CODE["4530"]) == []


def test_every_rule_key_has_a_description() -> None:
    from app.rule_engine.schema import EVIDENCE_DESCRIPTIONS

    for rule in RULES_BY_CODE.values():
        assert set(evidence_keys(rule)) <= EVIDENCE_DESCRIPTIONS.keys()
