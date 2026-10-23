"""End-to-end evaluation of the document AI pipeline on synthetic scans.

    python -m evals.run_eval --per-type 8 --out eval-report

Each document is generated from the corpus, rendered, randomly degraded
(rotation, shadow, noise, blur, JPEG), then sent through the production
pipeline: vision -> OCR -> classification -> evidence extraction. Ground truth
is known by construction. Exits 1 if any quality gate is missed, so CI blocks
changes that make the pipeline worse.
"""

import argparse
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
from rapidfuzz.distance import Levenshtein

from app.ai.extraction import extract_evidence
from app.ml.concepts import concept_for_key
from app.rule_engine.models import Rule
from app.vision.pipeline import analyze_document
from evals.synth import Degradation, render
from training.corpus import DOC_EVIDENCE, DOC_TYPES, EVIDENCE_TEMPLATES, make_document

GATES = {
    "doc_type_accuracy": 0.90,
    "evidence_f1": 0.80,
    "ocr_cer": 0.05,  # maximum
    "deskew_mae_degrees": 0.5,  # maximum
    "signature_f1": 0.80,
    "qr_decode_rate": 0.90,
}
MAXIMUM_GATES = {"ocr_cer", "deskew_mae_degrees"}

# A rule that asks for every evidence concept, so extraction is scored on all of them.
ALL_EVIDENCE = Rule("EVAL", "All evidence", {"type": "one_of", "options": list(EVIDENCE_TEMPLATES)})


@dataclass
class Tally:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, predicted: set[str], actual: set[str]) -> None:
        self.tp += len(predicted & actual)
        self.fp += len(predicted - actual)
        self.fn += len(actual - predicted)

    def scores(self) -> dict[str, float]:
        precision = self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0
        recall = self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


@dataclass
class Results:
    doc_type_correct: int = 0
    total: int = 0
    evidence: Tally = field(default_factory=Tally)
    signature: Tally = field(default_factory=Tally)
    cer: list[float] = field(default_factory=list)
    skew_error: list[float] = field(default_factory=list)
    qr_decoded: list[bool] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)
    confusions: list[dict[str, str]] = field(default_factory=list)


def evaluate(per_type: int, seed: int) -> dict[str, object]:
    rng = random.Random(seed)
    results = Results()
    for doc_type in DOC_TYPES:
        for _ in range(per_type):
            doc = make_document(doc_type, rng)
            # Signatures also appear on documents where no text claims one.
            doc.with_signature = doc.with_signature or rng.random() < 0.15
            degradation = Degradation.random(rng)
            ok, png = cv2.imencode(".png", render(doc, rng, degradation))
            assert ok

            started = time.perf_counter()
            analysis = analyze_document(png.tobytes(), "image/png")
            extraction = extract_evidence(ALL_EVIDENCE, analysis, None)
            results.latency_ms.append((time.perf_counter() - started) * 1000)

            results.total += 1
            if extraction.doc_type == doc_type:
                results.doc_type_correct += 1
            else:
                results.confusions.append({"expected": doc_type, "predicted": extraction.doc_type})

            predicted = {concept_for_key(c.key) for c in extraction.accepted if "ml" in c.sources}
            relevant = set(DOC_EVIDENCE[doc_type])  # concepts this document type can carry
            results.evidence.add(predicted & relevant, set(doc.evidence))
            results.evidence.fp += len(predicted - relevant)

            detected, present = {"sig"} if analysis.has_signature else set(), {"sig"} if doc.with_signature else set()
            results.signature.add(detected, present)
            truth = " ".join(doc.lines)
            results.cer.append(Levenshtein.distance(" ".join(analysis.text.split()), truth) / len(truth))
            results.skew_error.append(abs(analysis.pages[0].skew_degrees + degradation.rotation))
            if doc.qr_payload:
                results.qr_decoded.append(any(c.payload == doc.qr_payload for c in analysis.pages[0].codes))

    latency = sorted(results.latency_ms)
    evidence = results.evidence.scores()
    signature = results.signature.scores()
    return {
        "documents": results.total,
        "doc_type_accuracy": round(results.doc_type_correct / results.total, 4),
        "evidence_precision": evidence["precision"],
        "evidence_recall": evidence["recall"],
        "evidence_f1": evidence["f1"],
        "ocr_cer": round(statistics.mean(results.cer), 4),
        "deskew_mae_degrees": round(statistics.mean(results.skew_error), 3),
        "signature_precision": signature["precision"],
        "signature_recall": signature["recall"],
        "signature_f1": signature["f1"],
        "qr_decode_rate": round(sum(results.qr_decoded) / max(1, len(results.qr_decoded)), 4),
        "latency_p50_ms": round(latency[len(latency) // 2]),
        "latency_p95_ms": round(latency[min(len(latency) - 1, int(len(latency) * 0.95))]),
        "doc_type_confusions": results.confusions,
    }


def check_gates(report: dict[str, object]) -> list[str]:
    failures = []
    for metric, threshold in GATES.items():
        value = float(report[metric])  # type: ignore[arg-type]
        if (value > threshold) if metric in MAXIMUM_GATES else (value < threshold):
            bound = "<=" if metric in MAXIMUM_GATES else ">="
            failures.append(f"{metric} = {value} (gate {bound} {threshold})")
    return failures


def to_markdown(report: dict[str, object], failures: list[str]) -> str:
    rows = [f"| {k} | {v} | {GATES.get(k, '')} |" for k, v in report.items() if not isinstance(v, list)]
    status = "PASSED" if not failures else "FAILED: " + "; ".join(failures)
    return "\n".join(
        [
            "## Document AI evaluation",
            "",
            f"**Quality gates {status}**",
            "",
            "| metric | value | gate |",
            "|---|---|---|",
            *rows,
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-type", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path("eval-report"))
    args = parser.parse_args()

    report = evaluate(args.per_type, args.seed)
    failures = check_gates(report)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps({**report, "gates": GATES}, indent=2) + "\n")
    markdown = to_markdown(report, failures)
    (args.out / "report.md").write_text(markdown)
    print(markdown)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
