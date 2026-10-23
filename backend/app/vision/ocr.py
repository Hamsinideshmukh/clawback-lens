"""Text recognition with PaddleOCR's PP-OCR models (DB text detector + SVTR
recogniser) served through ONNX Runtime by RapidOCR. Unlike Tesseract's
layout-first pipeline it is robust to photos, receipts and low-contrast
scans, and it needs no Paddle or PyTorch runtime: CPU-only, ~20 MB of models.
See docs/ocr-survey.md for the engine comparison."""

import threading
from functools import lru_cache

import numpy as np

from app.vision.types import Box, OcrLine

_lock = threading.Lock()  # ONNX sessions are shared; serialise calls from worker threads


@lru_cache(maxsize=1)
def _engine():  # type: ignore[no-untyped-def]
    from rapidocr import RapidOCR

    # A wider unclip ratio than the default (1.6) keeps ascenders and descenders
    # inside the crop on deskewed, perfectly horizontal lines; with the default,
    # tight boxes occasionally clip glyphs and the recogniser returns garbage.
    return RapidOCR(params={"Det.unclip_ratio": 2.0})


def recognise(image: np.ndarray) -> list[OcrLine]:
    """Returns text lines in reading order with normalised boxes."""
    h, w = image.shape[:2]
    with _lock:
        result = _engine()(image)
    if result.boxes is None:
        return []

    lines = []
    for quad, text, score in zip(np.asarray(result.boxes), result.txts, result.scores, strict=True):
        text = str(text).strip()
        if not text:
            continue
        x0, y0 = quad.min(axis=0)
        x1, y1 = quad.max(axis=0)
        box = Box.from_pixels(float(x0), float(y0), float(x1 - x0), float(y1 - y0), w, h)
        lines.append(OcrLine(text=text, confidence=round(float(score), 4), box=box))

    # Reading order: rows by vertical centre (tolerance of half a line height), then left to right.
    row_height = float(np.median([line.box.h for line in lines])) or 0.01
    return sorted(lines, key=lambda line: (round((line.box.y + line.box.h / 2) / (row_height / 2)), line.box.x))


def warm_up() -> None:
    """Loads the ONNX sessions eagerly so the first request is not slow."""
    recognise(np.full((64, 256, 3), 255, np.uint8))
