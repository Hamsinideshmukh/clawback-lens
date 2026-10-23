"""Evidence extraction: turns a document analysis into rule-engine evidence.

Three independent signals are fused per evidence key:

* ML      — the ONNX sentence classifier scores every OCR line span; the best
            span for a key becomes its citation. Always available, offline.
* LLM     — optional. Must cite line numbers and quote them verbatim; quotes
            that cannot be found in the OCR text are discarded (grounding).
* Vision  — detected signatures and machine-readable codes corroborate, or
            undermine, what the text claims.

The output is candidate evidence with confidence and provenance. Whether that
evidence wins the dispute is decided only by the rule engine; whether it is
trusted enough to auto-resolve is decided by the workflow policy."""

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from rapidfuzz import fuzz

from app.ai import llm
from app.core.metrics import EVIDENCE_EXTRACTED
from app.ml.concepts import DOC_TYPE_TRANSACTION, concept_for_key
from app.ml.models import get_models
from app.ml.text import candidate_spans
from app.rule_engine.models import Rule
from app.rule_engine.schema import EVIDENCE_DESCRIPTIONS, keys_for_branch, transaction_types
from app.vision.types import DocumentAnalysis

logger = logging.getLogger(__name__)

ML_MIN_PROBABILITY = 0.45
MIN_LINE_CONFIDENCE = 0.80  # text spans use confidently read lines only (excludes scribbles OCR'd as words)
LLM_ONLY_CONFIDENCE = 0.70  # an uncorroborated LLM claim never clears auto-resolution
LLM_CORROBORATION = 0.80
GROUNDING_MIN_SCORE = 85
ACCEPT_THRESHOLD = 0.50
UNCONFIRMED_SIGNATURE_CAP = 0.75
VISUAL_KEYS = {
    "signed_delivery": ("signature", "Handwritten signature detected on the document"),
    "boarding_pass_scan": ("code", "Machine-readable boarding pass code detected"),
}


@dataclass
class EvidenceCandidate:
    key: str
    confidence: float
    citation: str
    sources: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    doc_type: str
    doc_type_confidence: float
    transaction_type: str | None
    candidates: list[EvidenceCandidate]
    model_version: str
    llm_used: bool = False
    llm_error: str | None = None
    rejected_llm_claims: list[dict[str, Any]] = field(default_factory=list)

    @property
    def accepted(self) -> list[EvidenceCandidate]:
        return [c for c in self.candidates if c.confidence >= ACCEPT_THRESHOLD]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_evidence(rule: Rule, analysis: DocumentAnalysis, transaction_type: str | None) -> ExtractionResult:
    models = get_models()
    lines = [line.text for line in analysis.lines if line.confidence >= MIN_LINE_CONFIDENCE]
    doc_type = models.doc_type.predict(analysis.text)

    if transaction_types(rule) and transaction_type is None:
        transaction_type = DOC_TYPE_TRANSACTION.get(doc_type.label)
    rule_keys = keys_for_branch(rule, transaction_type)

    ml_hits = _ml_candidates(lines, rule_keys)
    result = ExtractionResult(
        doc_type=doc_type.label,
        doc_type_confidence=doc_type.confidence,
        transaction_type=transaction_type,
        candidates=[],
        model_version=models.version,
    )

    llm_hits: dict[str, str] = {}
    try:
        llm_hits, result.rejected_llm_claims = _llm_candidates(lines, rule_keys)
        result.llm_used = True
    except llm.LLMUnavailable as exc:
        result.llm_error = str(exc)

    for key in rule_keys:
        candidate = _fuse(key, ml_hits.get(key), llm_hits.get(key), analysis, doc_type.label)
        if candidate:
            result.candidates.append(candidate)
    for candidate in result.accepted:
        for source in candidate.sources:
            EVIDENCE_EXTRACTED.labels(source).inc()
    return result


def _ml_candidates(lines: list[str], rule_keys: list[str]) -> dict[str, tuple[float, str]]:
    """Best (probability, span) per rule key, where the key's concept is the span's top class."""
    spans = candidate_spans(lines)
    if not spans:
        return {}
    classifier = get_models().evidence
    proba = classifier.predict_proba(spans)
    top = proba.argmax(axis=1)

    hits: dict[str, tuple[float, str]] = {}
    for key in rule_keys:
        concept = concept_for_key(key)
        if concept not in classifier.labels:
            continue
        col = classifier.labels.index(concept)
        rows = [i for i in range(len(spans)) if top[i] == col and proba[i, col] >= ML_MIN_PROBABILITY]
        if rows:
            best = max(rows, key=lambda i: proba[i, col])
            hits[key] = (round(float(proba[best, col]), 4), spans[best])
    return hits


def _llm_candidates(lines: list[str], rule_keys: list[str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    numbered = "\n".join(f"[{i}] {line}" for i, line in enumerate(lines))
    keys = "\n".join(f'- "{k}": {EVIDENCE_DESCRIPTIONS.get(k, k)}' for k in rule_keys)
    message = llm.chat(
        [
            {
                "role": "system",
                "content": "You extract evidence from OCR text of payment-dispute documents. "
                "Only report evidence the text explicitly states. Never decide the dispute. Respond with JSON.",
            },
            {
                "role": "user",
                "content": f"Evidence keys:\n{keys}\n\nOCR lines:\n{numbered}\n\n"
                'Return {"evidence": [{"key": <key>, "lines": [<line numbers>], '
                '"quote": <verbatim text from those lines>}]}. Omit keys the text does not support.',
            },
        ],
        purpose="extraction",
        json_mode=True,
    )
    claims = llm.parse_json(message.get("content")).get("evidence", [])

    grounded: dict[str, str] = {}
    rejected: list[dict[str, Any]] = []
    for claim in claims if isinstance(claims, list) else []:
        key, quote = claim.get("key"), str(claim.get("quote", ""))
        cited = " ".join(lines[i] for i in claim.get("lines", []) if isinstance(i, int) and 0 <= i < len(lines))
        if (
            key in rule_keys
            and quote
            and cited
            and fuzz.partial_ratio(quote.lower(), cited.lower()) >= GROUNDING_MIN_SCORE
        ):
            grounded[key] = cited
        else:
            rejected.append({"key": key, "quote": quote, "reason": "not grounded in OCR text"})
    if rejected:
        logger.info("rejected ungrounded llm claims", extra={"extra_fields": {"count": len(rejected)}})
    return grounded, rejected


def _fuse(
    key: str,
    ml_hit: tuple[float, str] | None,
    llm_citation: str | None,
    analysis: DocumentAnalysis,
    doc_type: str,
) -> EvidenceCandidate | None:
    sources: list[str] = []
    confidence, citation = 0.0, ""
    if ml_hit:
        confidence, citation = ml_hit
        sources.append("ml")
    if llm_citation:
        confidence = 1 - (1 - confidence) * (1 - LLM_CORROBORATION) if ml_hit else LLM_ONLY_CONFIDENCE
        citation = citation or llm_citation
        sources.append("llm")

    visual = VISUAL_KEYS.get(concept_for_key(key))
    if visual:
        kind, description = visual
        seen = analysis.has_signature if kind == "signature" else analysis.has_code
        if seen and (sources or doc_type in ("delivery_receipt", "boarding_pass")):
            # Visual confirmation corroborates the text, or stands alone as weaker evidence.
            confidence = 1 - (1 - confidence) * 0.4 if sources else 0.6
            citation = citation or description
            sources.append("vision")
        elif sources and kind == "signature":
            # The text claims a signature the detector cannot find: needs a human look.
            confidence = min(confidence, UNCONFIRMED_SIGNATURE_CAP)

    if not sources:
        return None
    # Poor OCR undermines every text-derived claim.
    confidence *= min(1.0, analysis.ocr_confidence / 0.85) if "vision" not in sources else 1.0
    return EvidenceCandidate(key, round(confidence, 4), citation, sources)
