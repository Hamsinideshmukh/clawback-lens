import json
from typing import Any

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.ml.models import get_models
from app.rule_engine.rules import RULES_BY_CODE
from app.rule_engine.schema import EVIDENCE_DESCRIPTIONS, evidence_keys, transaction_types
from app.schemas.case import ReasonCodeOut

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Readiness: database reachable and models loaded."""
    db.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "model_version": get_models().version,
        "llm_enabled": get_settings().llm_enabled,
    }


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/reason-codes", response_model=list[ReasonCodeOut])
def reason_codes() -> list[ReasonCodeOut]:
    return [
        ReasonCodeOut(
            reason_code=rule.reason_code,
            name=rule.name,
            always_escalate=rule.always_escalate,
            transaction_types=transaction_types(rule),
            evidence={key: EVIDENCE_DESCRIPTIONS.get(key, key) for key in evidence_keys(rule)},
        )
        for rule in sorted(RULES_BY_CODE.values(), key=lambda r: r.reason_code)
    ]


@router.get("/api/v1/models")
def model_card() -> dict[str, Any]:
    """The model card of the ONNX models currently served."""
    return dict(json.loads((get_settings().model_dir / "model_card.json").read_text()))
