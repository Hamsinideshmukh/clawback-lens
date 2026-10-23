import json
import shutil
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.ml.concepts import concept_for_key, keys_for_concept
from app.ml.models import ModelIntegrityError, TextClassifier, get_models
from app.ml.text import candidate_spans, normalize


def test_normalize_folds_digits_case_synonyms_and_suffixes() -> None:
    assert normalize("Signed for by A. Singh on 2026-07-24!") == "sign for by a singh on 0000 00 00"
    assert normalize("The parcel was countersigned") == normalize("the package was signed")


def test_candidate_spans_cover_single_lines_and_wrapped_pairs() -> None:
    assert candidate_spans(["a", "b", "c"]) == ["a", "a b", "b", "b c", "c"]


def test_concepts_resolve_to_the_rule_specific_key() -> None:
    assert concept_for_key("signed_carrier_delivery_receipt") == "signed_delivery"
    assert keys_for_concept("signed_delivery", ["signed_carrier_delivery_receipt", "x"]) == [
        "signed_carrier_delivery_receipt"
    ]
    assert concept_for_key("ip_address_match") == "ip_address_match"


@pytest.mark.parametrize(
    ("sentence", "concept"),
    [
        ("Parcel handed over and signed for by the customer.", "signed_delivery"),
        ("We issued a full refund to the cardholder's card yesterday.", "correcting_transaction_processed"),
        ("Passenger boarding scan recorded at gate B12.", "boarding_pass_scan"),
        ("Subtotal $45.00", "none"),
    ],
)
def test_evidence_classifier_on_unseen_phrasings(sentence: str, concept: str) -> None:
    assert get_models().evidence.predict(sentence).label == concept


def test_doc_type_classifier() -> None:
    text = "BOARDING PASS Passenger: Maria Garcia Flight BA117 Gate C4 Seat 14A"
    assert get_models().doc_type.predict(text).label == "boarding_pass"


def test_tampered_model_is_rejected(tmp_path: Path) -> None:
    model_dir = get_settings().model_dir
    card = json.loads((model_dir / "model_card.json").read_text())["models"]["doc_type"]
    tampered = tmp_path / "doc_type.onnx"
    shutil.copy(model_dir / "doc_type.onnx", tampered)
    tampered.write_bytes(tampered.read_bytes() + b"\0")
    with pytest.raises(ModelIntegrityError):
        TextClassifier(tampered, card)
