"""Visual evidence detectors: handwritten signatures and machine-readable codes."""

import cv2
import numpy as np

from app.vision.types import Box, CodeRegion, OcrLine, SignatureRegion

MIN_SIGNATURE_SCORE = 0.5
CONFIDENT_PRINT = 0.9  # OCR confidence above which a line is printed text whatever its height


def detect_codes(views: list[np.ndarray]) -> list[CodeRegion]:
    """QR codes (boarding passes, shipping labels) and 1-D barcodes (tracking numbers).

    Decoders are brittle to blur, noise and JPEG artefacts, and each image
    variant (deskewed, binarized, original) fails on different inputs, so the
    views are tried in order and the first that yields a code wins."""
    for view in views:
        found = _decode(view if view.ndim == 3 else cv2.cvtColor(view, cv2.COLOR_GRAY2BGR))
        if found:
            return found
    return []


def _decode(image: np.ndarray) -> list[CodeRegion]:
    h, w = image.shape[:2]
    found: list[CodeRegion] = []

    ok, payloads, points, _ = cv2.QRCodeDetector().detectAndDecodeMulti(image)
    if ok and points is not None:
        for payload, quad in zip(payloads, points, strict=True):
            if payload:
                found.append(CodeRegion("qr", payload, _quad_box(quad, w, h)))

    ok, payloads, _types, points = cv2.barcode.BarcodeDetector().detectAndDecodeWithType(image)
    if ok and points is not None:
        for payload, quad in zip(payloads, points, strict=True):
            if payload:
                found.append(CodeRegion("barcode", payload, _quad_box(quad, w, h)))
    return found


def detect_signatures(binary: np.ndarray, lines: list[OcrLine], codes: list[CodeRegion]) -> list[SignatureRegion]:
    """Finds handwriting-like ink that the OCR engine did not read as text.

    1. Ink inside confidently-read, normal-height text lines and code regions is
       erased, which removes printed content. OCR engines happily "read" a
       scribble as a word, but its box is much taller than a printed line and
       its confidence low; height and confidence together separate the two.
    2. Remaining strokes are merged into blobs with a morphological close.
    3. Each blob is scored on geometry typical of a signature: wide, short,
       sparse, curvy ink (low solidity) rather than rules, boxes or noise.
    """
    h, w = binary.shape
    ink = (binary == 0).astype(np.uint8)

    printed = [line for line in lines if line.confidence >= 0.6 and sum(c.isalnum() for c in line.text) >= 3]
    if printed:
        max_height = 1.8 * float(np.median([line.box.h for line in printed]))
        for line in printed:
            # Large titles are taller than body text but read with high confidence; scribbles are not.
            if line.box.h <= max_height or line.confidence >= CONFIDENT_PRINT:
                _erase(ink, line.box, w, h, pad=0.004)
    for code in codes:
        _erase(ink, code.box, w, h, pad=0.01)

    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    merge = max(9, round(w * 0.012))
    blobs = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (merge, merge)))
    contours, _ = cv2.findContours(blobs, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        score = _signature_score(ink[y : y + bh, x : x + bw], bw / w, bh / h, contour)
        if score >= MIN_SIGNATURE_SCORE:
            regions.append(SignatureRegion(Box.from_pixels(x, y, bw, bh, w, h), round(score, 3)))
    return sorted(regions, key=lambda r: -r.score)[:3]


def _signature_score(patch: np.ndarray, rel_w: float, rel_h: float, contour: np.ndarray) -> float:
    if rel_w < 0.06 or rel_h < 0.015 or rel_w > 0.7 or rel_h > 0.25:
        return 0.0
    aspect = patch.shape[1] / patch.shape[0]
    density = float(patch.mean())
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = cv2.contourArea(contour) / hull_area if hull_area else 1.0

    # Thin straight strokes ("________") are rules, not signatures.
    ink_rows = np.flatnonzero(patch.sum(axis=1))
    vertical_extent = (ink_rows[-1] - ink_rows[0] + 1) / patch.shape[0] if ink_rows.size else 0.0

    return (
        _band(aspect, 1.2, 2.0, 10.0, 16.0)
        * _band(density, 0.02, 0.04, 0.25, 0.4)
        * _band(solidity, 0.0, 0.0, 0.75, 0.95)
        * _band(vertical_extent, 0.3, 0.5, 1.0, 1.01)
    )


def _band(value: float, lo: float, lo_full: float, hi_full: float, hi: float) -> float:
    """Trapezoidal membership: 0 outside [lo, hi], 1 inside [lo_full, hi_full]."""
    if value <= lo or value >= hi:
        return 0.0
    if value < lo_full:
        return (value - lo) / (lo_full - lo)
    if value > hi_full:
        return (hi - value) / (hi - hi_full)
    return 1.0


def _erase(mask: np.ndarray, box: Box, w: int, h: int, pad: float) -> None:
    x0, y0 = max(0, int((box.x - pad) * w)), max(0, int((box.y - pad) * h))
    x1, y1 = min(w, int((box.x + box.w + pad) * w) + 1), min(h, int((box.y + box.h + pad) * h) + 1)
    mask[y0:y1, x0:x1] = 0


def _quad_box(quad: np.ndarray, w: int, h: int) -> Box:
    quad = np.asarray(quad).reshape(-1, 2)
    x0, y0 = quad.min(axis=0)
    x1, y1 = quad.max(axis=0)
    return Box.from_pixels(float(x0), float(y0), float(x1 - x0), float(y1 - y0), w, h)
