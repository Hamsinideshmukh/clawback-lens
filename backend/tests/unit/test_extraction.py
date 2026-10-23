from typing import Any

import pytest

from app.ai import extraction, llm
from app.rule_engine.rules import RULES_BY_CODE
from app.vision.types import Box, CodeRegion, DocumentAnalysis, OcrLine, PageAnalysis, SignatureRegion

BOX = Box(0.1, 0.1, 0.5, 0.02)


def make_analysis(
    lines: list[str], *, signature: bool = False, qr: bool = False, conf: float = 0.98
) -> DocumentAnalysis:
    page = PageAnalysis(
        index=0,
        width=1240,
        height=1754,
        skew_degrees=0.0,
        quality={},
        lines=[OcrLine(text, conf, BOX) for text in lines],
        signatures=[SignatureRegion(BOX, 0.9)] if signature else [],
        codes=[CodeRegion("qr", "BA117|M GARCIA|14A", BOX)] if qr else [],
    )
    return DocumentAnalysis(pages=[page], timings_ms={})


RECEIPT = [
    "Northwind Goods - Proof of Delivery",
    "Delivered: 2026-03-02 14:10",
    "Signed for by Maria Garcia at the door.",
]


def test_ml_extracts_and_vision_corroborates_a_signature() -> None:
    result = extraction.extract_evidence(RULES_BY_CODE["4554"], make_analysis(RECEIPT, signature=True), None)
    assert result.doc_type == "delivery_receipt"
    assert result.transaction_type == "physical_goods"
    [candidate] = result.accepted
    assert candidate.key == "signed_delivery_receipt"
    assert candidate.sources == ["ml", "vision"]
    assert candidate.confidence > 0.95
    assert "Signed for by Maria Garcia" in candidate.citation
    assert result.llm_used is False


def test_claimed_signature_without_visual_confirmation_is_capped_below_auto_resolve() -> None:
    result = extraction.extract_evidence(RULES_BY_CODE["4554"], make_analysis(RECEIPT), None)
    [candidate] = result.accepted
    assert candidate.confidence <= extraction.UNCONFIRMED_SIGNATURE_CAP


def test_concept_maps_to_the_key_used_by_the_case_rule() -> None:
    result = extraction.extract_evidence(RULES_BY_CODE["4540"], make_analysis(RECEIPT, signature=True), None)
    assert [c.key for c in result.accepted] == ["signed_carrier_delivery_receipt"]


def test_poor_ocr_lowers_confidence() -> None:
    lines = ["A refund of $40.00 was processed."]
    clean = extraction.extract_evidence(RULES_BY_CODE["4530"], make_analysis(lines), None)
    noisy = extraction.extract_evidence(RULES_BY_CODE["4530"], make_analysis(lines, conf=0.82), None)
    assert noisy.candidates[0].confidence < clean.candidates[0].confidence


def test_irrelevant_document_yields_no_evidence() -> None:
    lines = ["INVOICE", "Subtotal $45.00", "Thank you for shopping with us."]
    assert extraction.extract_evidence(RULES_BY_CODE["4530"], make_analysis(lines), None).accepted == []


def test_grounded_llm_claim_is_fused_and_ungrounded_claim_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = ["Message from Orbit Retail", "We have refunded the customer in full.", "Kind regards"]

    def fake_chat(messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        return {
            "content": '{"evidence": ['
            '{"key": "correcting_transaction_processed", "lines": [1], "quote": "refunded the customer in full"},'
            '{"key": "chargeback_raised_in_error", "lines": [2], "quote": "the cardholder withdrew the dispute"}]}'
        }

    monkeypatch.setattr(llm, "chat", fake_chat)
    result = extraction.extract_evidence(RULES_BY_CODE["4530"], make_analysis(lines), None)

    assert result.llm_used
    [candidate] = result.accepted
    assert candidate.key == "correcting_transaction_processed"
    assert candidate.sources == ["ml", "llm"]
    assert [r["key"] for r in result.rejected_llm_claims] == ["chargeback_raised_in_error"]


def test_llm_only_claim_cannot_clear_auto_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = ["Note from merchant", "Customer phoned and said to drop the case, they made the purchase."]
    monkeypatch.setattr(
        llm,
        "chat",
        lambda *_a, **_k: {
            "content": '{"evidence": [{"key": "chargeback_raised_in_error", "lines": [1], '
            '"quote": "said to drop the case, they made the purchase"}]}'
        },
    )
    result = extraction.extract_evidence(RULES_BY_CODE["4530"], make_analysis(lines), None)
    llm_only = [c for c in result.candidates if c.sources == ["llm"]]
    assert all(c.confidence < 0.8 for c in llm_only)


def test_llm_failure_falls_back_to_local_models(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise llm.LLMUnavailable("timeout")

    monkeypatch.setattr(llm, "chat", broken)
    result = extraction.extract_evidence(RULES_BY_CODE["4554"], make_analysis(RECEIPT, signature=True), None)
    assert result.llm_error == "timeout"
    assert result.accepted


def test_boarding_pass_code_corroborates_travel_evidence() -> None:
    lines = ["BOARDING PASS", "Passenger: Maria Garcia", "Flight BA117", "Gate C4 Seat 14A"]
    result = extraction.extract_evidence(RULES_BY_CODE["4554"], make_analysis(lines, qr=True), None)
    assert result.transaction_type == "travel"
    assert any(c.key == "boarding_pass_scan" and "vision" in c.sources for c in result.accepted)


def test_parse_json_tolerates_fences_and_rejects_garbage() -> None:
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(llm.LLMUnavailable):
        llm.parse_json("not json")


def test_llm_disabled_without_api_key() -> None:
    with pytest.raises(llm.LLMUnavailable, match="not configured"):
        llm.chat([], purpose="test")
