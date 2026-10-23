"""Trains the document-type and evidence-sentence classifiers, exports them to
ONNX, and writes a model card with held-out metrics.

    python -m training.train [--out models/]   # train, gate, export
    python -m training.train --check            # CI: committed models == clean retrain

Metrics come from cross-validation grouped by template, so they measure
generalisation to phrasings the model never saw. The run is deterministic
(fixed seed), fails with exit code 1 when a quality gate is missed, and
verifies that the ONNX graph reproduces scikit-learn's probabilities before
anything is written, so CI can retrain from scratch and block a regression.
"""

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from skl2onnx import to_onnx
from skl2onnx.common.data_types import StringTensorType
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

from app.ml.text import normalize
from training.corpus import (
    DOC_FIELDS,
    DOC_HEADERS,
    DOC_TYPES,
    NONE_LABEL,
    Sample,
    evidence_sentences,
    fill,
    make_document,
)

SEED = 20261021
TOKEN_PATTERN = r"\b\w\w+\b"
CV_FOLDS = 4
C_GRID = (2.0, 8.0, 32.0)
# Regression floors just below the current baseline; CI fails if a change drops below them.
GATES = {"evidence": {"macro_f1": 0.80}, "doc_type": {"accuracy": 0.95}}


@dataclass
class Dataset:
    texts: list[str]
    labels: list[str]
    groups: list[str]


def build_evidence_dataset(rng: random.Random) -> Dataset:
    samples = evidence_sentences(rng)
    # Field lines ("Tracking number: ...") and headers are realistic negatives.
    for doc_type in DOC_TYPES:
        for i, template in enumerate(DOC_FIELDS[doc_type] + DOC_HEADERS[doc_type]):
            for _ in range(6):
                samples.append(Sample(fill(template, rng), NONE_LABEL, f"field:{doc_type}:{i}"))
    return Dataset([normalize(s.text) for s in samples], [s.label for s in samples], [s.group for s in samples])


def build_doc_type_dataset(rng: random.Random, per_type: int = 200) -> Dataset:
    data = Dataset([], [], [])
    for doc_type in DOC_TYPES:
        for _ in range(per_type):
            doc = make_document(doc_type, rng)
            data.texts.append(normalize(" ".join(doc.lines)))
            data.labels.append(doc_type)
            data.groups.append(doc.group)
    return data


def make_pipeline(c: float) -> Pipeline:
    # sublinear_tf is deliberately off: skl2onnx's TfIdfVectorizer op does not
    # reproduce sklearn's log-scaled counts for repeated n-grams.
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(lowercase=False, token_pattern=TOKEN_PATTERN)),
            ("clf", LogisticRegression(C=c, max_iter=3000, class_weight="balanced")),
        ]
    )


def grouped_cv_predict(data: Dataset, c: float, folds: int = CV_FOLDS) -> list[str]:
    """Out-of-fold predictions where no template appears in both train and validation."""
    predicted = [""] * len(data.texts)
    for train_idx, val_idx in GroupKFold(n_splits=folds).split(data.texts, data.labels, data.groups):
        model = make_pipeline(c).fit([data.texts[i] for i in train_idx], [data.labels[i] for i in train_idx])
        for i, label in zip(val_idx, model.predict([data.texts[i] for i in val_idx]), strict=True):
            predicted[i] = str(label)
    return predicted


def export_onnx(model: Pipeline, probe: list[str]) -> bytes:
    tfidf, clf = model.named_steps["tfidf"], model.named_steps["clf"]
    onnx_model = to_onnx(
        model,
        initial_types=[("text", StringTensorType([None, 1]))],
        options={id(clf): {"zipmap": False}, id(tfidf): {"tokenexp": TOKEN_PATTERN}},
        target_opset=17,
    )
    # skl2onnx collects opset domains in a set, so their order (and the file's bytes)
    # depends on PYTHONHASHSEED. Sorting them makes the export byte-for-byte reproducible.
    opsets = sorted(onnx_model.opset_import, key=lambda opset: opset.domain)
    del onnx_model.opset_import[:]
    onnx_model.opset_import.extend(opsets)
    payload = onnx_model.SerializeToString()

    import onnxruntime as ort

    session = ort.InferenceSession(payload, providers=["CPUExecutionProvider"])
    onnx_proba = session.run(None, {"text": np.array(probe, dtype=object).reshape(-1, 1)})[1]
    drift = float(np.abs(onnx_proba - model.predict_proba(probe)).max())
    if drift > 1e-4:
        raise RuntimeError(f"ONNX export diverges from scikit-learn (max |dp| = {drift:.2e})")
    return payload


def train_model(name: str, data: Dataset) -> tuple[bytes, dict]:
    cv = {c: grouped_cv_predict(data, c) for c in C_GRID}
    c = max(C_GRID, key=lambda c: f1_score(data.labels, cv[c], average="macro"))
    predicted = cv[c]
    report = classification_report(data.labels, predicted, output_dict=True, zero_division=0)
    metrics = {
        "accuracy": round(accuracy_score(data.labels, predicted), 4),
        "macro_f1": round(f1_score(data.labels, predicted, average="macro"), 4),
        "per_class_f1": {k: round(v["f1-score"], 4) for k, v in report.items() if k in set(data.labels)},
    }

    model = make_pipeline(c).fit(data.texts, data.labels)
    payload = export_onnx(model, data.texts[::7])
    card = {
        "file": f"{name}.onnx",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "labels": [str(label) for label in model.classes_],
        "algorithm": "tf-idf (stemmed unigrams) + logistic regression",
        "hyperparameters": {"C": c},
        "samples": len(data.texts),
        "evaluation": f"{CV_FOLDS}-fold cross-validation grouped by template (unseen phrasings)",
        "metrics": metrics,
    }
    return payload, card


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "models")
    parser.add_argument(
        "--check", action="store_true", help="verify the models in --out are reproducible from source; write nothing"
    )
    args = parser.parse_args()
    rng = random.Random(SEED)

    results = {
        "evidence": train_model("evidence", build_evidence_dataset(rng)),
        "doc_type": train_model("doc_type", build_doc_type_dataset(rng)),
    }

    failures = [
        f"{name}.{metric} = {results[name][1]['metrics'][metric]} < {threshold}"
        for name, gates in GATES.items()
        for metric, threshold in gates.items()
        if results[name][1]["metrics"][metric] < threshold
    ]
    for name, (_, card) in results.items():
        print(f"{name}: {json.dumps(card['metrics'], indent=None)}")
    if failures:
        print("Quality gate failed:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1

    if args.check:
        committed = json.loads((args.out / "model_card.json").read_text())["models"]
        stale = [name for name, (_, card) in results.items() if committed[name]["sha256"] != card["sha256"]]
        if stale:
            print(f"Committed models are not reproducible from source: {stale}. Retrain and commit.", file=sys.stderr)
            return 1
        print("Committed models match a clean retrain.")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    for name, (payload, _) in results.items():
        (args.out / f"{name}.onnx").write_bytes(payload)
    model_card = {
        "version": datetime.now(UTC).strftime("%Y.%m.%d"),
        "seed": SEED,
        "gates": GATES,
        "models": {name: card for name, (_, card) in results.items()},
    }
    (args.out / "model_card.json").write_text(json.dumps(model_card, indent=2) + "\n")
    print(f"Wrote models to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
