import random

import cv2
import numpy as np
import pytest

from app.vision import preprocess
from app.vision.detectors import detect_codes
from app.vision.loader import UnsupportedDocument, load_pages
from app.vision.pipeline import analyze_document
from evals.synth import Degradation, render
from tests.conftest import render_png
from training.corpus import SyntheticDocument, make_document


def _gray_page(rng: random.Random, rotation: float = 0.0, shadow: bool = False) -> np.ndarray:
    image = render(make_document("invoice", rng), rng, Degradation(rotation=rotation, shadow=shadow))
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def test_native_sauvola_matches_numpy_reference(rng: random.Random) -> None:
    pytest.importorskip("clawback_native")
    gray = _gray_page(rng, shadow=True)[:600, :500]
    native = preprocess.sauvola(gray)
    reference = preprocess.sauvola_reference(gray)
    # Floating-point summation order differs; allow a handful of boundary pixels.
    assert (native != reference).mean() < 1e-4


def test_sauvola_survives_uneven_illumination(rng: random.Random) -> None:
    gray = _gray_page(rng, shadow=True)
    global_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    adaptive = preprocess.sauvola(gray)
    # In the shadowed left third, Otsu turns the background black; Sauvola keeps it white.
    left = slice(0, gray.shape[1] // 6)
    assert (adaptive[:, left] == 255).mean() > 0.9
    assert (global_otsu[:, left] == 255).mean() < (adaptive[:, left] == 255).mean()


@pytest.mark.parametrize("rotation", [-6.0, -2.5, 0.0, 4.0])
def test_deskew_recovers_rotation(rng: random.Random, rotation: float) -> None:
    binary = preprocess.sauvola(_gray_page(rng, rotation=rotation))
    assert preprocess.estimate_skew(binary) == pytest.approx(-rotation, abs=0.3)


def test_quality_flags_blur(rng: random.Random) -> None:
    gray = _gray_page(rng)
    assert not preprocess.assess_quality(gray)["blurry"]
    assert preprocess.assess_quality(cv2.GaussianBlur(gray, (15, 15), 5))["blurry"]


def test_qr_code_is_decoded(rng: random.Random) -> None:
    doc = make_document("boarding_pass", rng)
    codes = detect_codes([render(doc, rng)])
    assert [c.payload for c in codes if c.kind == "qr"] == [doc.qr_payload]


def test_loader_rejects_unsupported_and_corrupt_input() -> None:
    with pytest.raises(UnsupportedDocument):
        load_pages(b"hello", "text/plain", 3)
    with pytest.raises(UnsupportedDocument):
        load_pages(b"not a png", "image/png", 3)


def test_loader_renders_pdf_pages() -> None:
    pdfium = pytest.importorskip("pypdfium2")
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(612, 792)
    pdf.new_page(612, 792)
    import io

    buffer = io.BytesIO()
    pdf.save(buffer)
    pages = load_pages(buffer.getvalue(), "application/pdf", max_pages=1)
    assert len(pages) == 1
    assert pages[0].shape[1] == round(612 * 200 / 72)


@pytest.mark.slow
def test_pipeline_reads_text_and_finds_the_signature(delivery_receipt_png: bytes) -> None:
    analysis = analyze_document(delivery_receipt_png, "image/png")
    assert "signed for by Aarav Singh" in analysis.text
    assert analysis.ocr_confidence > 0.9
    assert analysis.has_signature
    assert analysis.pages[0].skew_degrees == pytest.approx(-3.0, abs=0.3)
    assert analysis.preview_jpeg.startswith(b"\xff\xd8")
    assert {"decode", "binarize", "deskew", "ocr", "signatures"} <= analysis.timings_ms.keys()


@pytest.mark.slow
def test_printed_text_alone_is_not_mistaken_for_a_signature(rng: random.Random) -> None:
    doc = SyntheticDocument("invoice", ["INVOICE", "Bill to: Maria Garcia", "Total $120.00", "Thank you"])
    assert not analyze_document(render_png(doc, rng), "image/png").has_signature
