import os

# Must be set before app modules read settings.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://clawback:clawback@localhost:5432/clawback_test")
os.environ["WORKER_EMBEDDED"] = "false"
os.environ["LLM_API_KEY"] = ""

import random

import cv2
import pytest

from evals.synth import Degradation, render
from training.corpus import SyntheticDocument


@pytest.fixture
def rng() -> random.Random:
    return random.Random(1234)


def render_png(doc: SyntheticDocument, rng: random.Random, degradation: Degradation | None = None) -> bytes:
    ok, buffer = cv2.imencode(".png", render(doc, rng, degradation))
    assert ok
    return buffer.tobytes()


@pytest.fixture
def delivery_receipt_png(rng: random.Random) -> bytes:
    doc = SyntheticDocument(
        doc_type="delivery_receipt",
        lines=[
            "Orbit Retail - Delivery Confirmation",
            "Tracking number: 774512093311",
            "Recipient: Aarav Singh",
            "The package was signed for by Aarav Singh on 2026-07-24.",
            "Status: Delivered",
        ],
        evidence=["signed_delivery"],
        with_signature=True,
    )
    return render_png(doc, rng, Degradation(rotation=3.0, noise_sigma=4.0))
