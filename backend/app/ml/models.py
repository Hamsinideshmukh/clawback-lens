"""ONNX Runtime serving for the classifiers trained by `training/train.py`.

Models are loaded once per process from the directory named in settings and
verified against the SHA-256 recorded in model_card.json, so a stale or
tampered artifact fails at startup instead of silently changing predictions."""

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from app.core.config import get_settings
from app.ml.text import normalize

ort.disable_telemetry_events()


class ModelIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float


class TextClassifier:
    def __init__(self, path: Path, card: dict[str, Any]) -> None:
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != card["sha256"]:
            raise ModelIntegrityError(f"{path.name}: sha256 {digest[:12]} does not match model card")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1  # tiny linear models; avoid thread oversubscription
        self._session = ort.InferenceSession(payload, options, providers=["CPUExecutionProvider"])
        self.labels: list[str] = card["labels"]
        self.metrics: dict[str, Any] = card["metrics"]

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, len(self.labels)), np.float32)
        batch = np.array([normalize(t) for t in texts], dtype=object).reshape(-1, 1)
        return np.asarray(self._session.run(None, {"text": batch})[1])

    def predict(self, text: str) -> Prediction:
        proba = self.predict_proba([text])[0]
        best = int(proba.argmax())
        return Prediction(self.labels[best], round(float(proba[best]), 4))


@dataclass(frozen=True)
class ModelRegistry:
    version: str
    doc_type: TextClassifier
    evidence: TextClassifier


@lru_cache(maxsize=1)
def get_models() -> ModelRegistry:
    model_dir = get_settings().model_dir
    card = json.loads((model_dir / "model_card.json").read_text())
    return ModelRegistry(
        version=card["version"],
        doc_type=TextClassifier(model_dir / "doc_type.onnx", card["models"]["doc_type"]),
        evidence=TextClassifier(model_dir / "evidence.onnx", card["models"]["evidence"]),
    )
