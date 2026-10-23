"""Document vision pipeline:

    decode -> quality -> binarize (C++) -> deskew -> OCR (PP-OCR/ONNX)
           -> code detection -> signature detection -> preview

Each stage is timed into a Prometheus histogram and the per-document
`timings_ms`, so slow stages are visible both in dashboards and in the UI."""

import time
from collections.abc import Callable
from typing import TypeVar

import cv2
import numpy as np

from app.core.metrics import PIPELINE_STAGE_SECONDS
from app.vision import detectors, ocr, preprocess
from app.vision.loader import load_pages
from app.vision.types import DocumentAnalysis, PageAnalysis

T = TypeVar("T")
PREVIEW_WIDTH = 1000


class _Timer:
    def __init__(self) -> None:
        self.timings: dict[str, float] = {}

    def run(self, stage: str, fn: Callable[[], T]) -> T:
        start = time.perf_counter()
        result = fn()
        elapsed = time.perf_counter() - start
        PIPELINE_STAGE_SECONDS.labels(stage).observe(elapsed)
        self.timings[stage] = round(self.timings.get(stage, 0.0) + elapsed * 1000, 1)
        return result


def analyze_document(content: bytes, content_type: str, max_pages: int = 3) -> DocumentAnalysis:
    timer = _Timer()
    images = timer.run("decode", lambda: load_pages(content, content_type, max_pages))

    pages: list[PageAnalysis] = []
    preview = b""
    for index, image in enumerate(images):
        page, deskewed = _analyze_page(index, image, timer)
        pages.append(page)
        if index == 0:
            preview = timer.run("preview", lambda img=deskewed: _encode_preview(img))  # type: ignore[misc]

    return DocumentAnalysis(pages=pages, timings_ms=timer.timings, preview_jpeg=preview)


def _analyze_page(index: int, image: np.ndarray, timer: _Timer) -> tuple[PageAnalysis, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    quality = timer.run("quality", lambda: preprocess.assess_quality(gray))

    binary = timer.run("binarize", lambda: preprocess.sauvola(gray))
    angle = timer.run("deskew", lambda: preprocess.estimate_skew(binary))
    original = image
    image = preprocess.deskew(image, angle)
    binary = preprocess.deskew(binary, angle)

    lines = timer.run("ocr", lambda: ocr.recognise(image))
    codes = timer.run("codes", lambda: detectors.detect_codes([image, binary, original]))
    signatures = timer.run("signatures", lambda: detectors.detect_signatures(binary, lines, codes))

    h, w = gray.shape
    page = PageAnalysis(
        index=index,
        width=w,
        height=h,
        skew_degrees=angle,
        quality=quality,
        lines=lines,
        signatures=signatures,
        codes=codes,
    )
    return page, image


def _encode_preview(image: np.ndarray) -> bytes:
    h, w = image.shape[:2]
    if w > PREVIEW_WIDTH:
        image = cv2.resize(image, (PREVIEW_WIDTH, round(h * PREVIEW_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buffer.tobytes() if ok else b""
