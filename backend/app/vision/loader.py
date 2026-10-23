"""Decodes uploaded bytes into page images (BGR uint8)."""

import cv2
import numpy as np
import pypdfium2 as pdfium

SUPPORTED_TYPES = {
    "application/pdf": "pdf",
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "image/tiff": "image",
}
PDF_RENDER_DPI = 200
MAX_SIDE_PX = 2400  # bounds memory and OCR latency for very large photos


class UnsupportedDocument(ValueError):
    pass


def load_pages(content: bytes, content_type: str, max_pages: int) -> list[np.ndarray]:
    kind = SUPPORTED_TYPES.get(content_type)
    if kind is None:
        raise UnsupportedDocument(f"Unsupported content type {content_type!r}; upload a PDF or image")
    pages = _render_pdf(content, max_pages) if kind == "pdf" else [_decode_image(content)]
    return [_limit_size(page) for page in pages]


def _render_pdf(content: bytes, max_pages: int) -> list[np.ndarray]:
    try:
        pdf = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as exc:
        raise UnsupportedDocument("Could not open PDF") from exc
    pages = []
    for index in range(min(len(pdf), max_pages)):
        rgb = pdf[index].render(scale=PDF_RENDER_DPI / 72).to_numpy()
        pages.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not pages:
        raise UnsupportedDocument("PDF has no pages")
    return pages


def _decode_image(content: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedDocument("Could not decode image")
    return image


def _limit_size(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    scale = MAX_SIDE_PX / max(h, w)
    if scale >= 1:
        return image
    return cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
