"""Typed results of the vision pipeline. Boxes are normalised to [0, 1]
relative to the deskewed page, so the frontend can overlay them on the
preview image at any display size."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @classmethod
    def from_pixels(cls, x: float, y: float, w: float, h: float, page_w: int, page_h: int) -> "Box":
        return cls(round(x / page_w, 4), round(y / page_h, 4), round(w / page_w, 4), round(h / page_h, 4))


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    box: Box


@dataclass(frozen=True)
class SignatureRegion:
    box: Box
    score: float


@dataclass(frozen=True)
class CodeRegion:
    kind: str  # qr | barcode
    payload: str
    box: Box


@dataclass
class PageAnalysis:
    index: int
    width: int
    height: int
    skew_degrees: float
    quality: dict[str, float | bool]
    lines: list[OcrLine] = field(default_factory=list)
    signatures: list[SignatureRegion] = field(default_factory=list)
    codes: list[CodeRegion] = field(default_factory=list)


@dataclass
class DocumentAnalysis:
    pages: list[PageAnalysis]
    timings_ms: dict[str, float]
    preview_jpeg: bytes = field(repr=False, default=b"")

    @property
    def lines(self) -> list[OcrLine]:
        return [line for page in self.pages for line in page.lines]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def ocr_confidence(self) -> float:
        lines = self.lines
        if not lines:
            return 0.0
        # Weight by text length so a long, well-read paragraph outweighs a stray glyph.
        total = sum(len(line.text) for line in lines)
        return round(sum(line.confidence * len(line.text) for line in lines) / total, 4)

    @property
    def has_signature(self) -> bool:
        return any(page.signatures for page in self.pages)

    @property
    def has_code(self) -> bool:
        return any(page.codes for page in self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {"pages": [asdict(page) for page in self.pages], "timings_ms": self.timings_ms}
