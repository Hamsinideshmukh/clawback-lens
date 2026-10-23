"""Read-only tools the case copilot can call. Each takes the case and returns
structured JSON; none can modify evidence or produce a verdict of its own
(`evaluate_case` previews the rule engine without persisting)."""

from collections.abc import Callable
from typing import Any

from app.db.models import Case
from app.services import adjudication_service

Tool = Callable[[Case], Any]


def get_case(case: Case) -> dict[str, Any]:
    return {
        "id": case.id,
        "reason_code": case.reason_code,
        "merchant": case.merchant_name,
        "amount": f"{case.amount} {case.currency}",
        "transaction_type": case.transaction_type,
        "status": case.status,
        "outcome": case.outcome,
        "respond_by": case.respond_by.isoformat(),
    }


def get_evidence(case: Case) -> list[dict[str, Any]]:
    return [
        {"key": e.key, "status": e.status, "source": e.source, "confidence": e.confidence, "citation": e.citation}
        for e in case.evidence
    ]


def get_documents(case: Case) -> list[dict[str, Any]]:
    return [
        {
            "filename": d.filename,
            "status": d.status,
            "doc_type": d.doc_type,
            "ocr_confidence": d.ocr_confidence,
            "signature_detected": any(p["signatures"] for p in (d.analysis or {}).get("pages", [])),
        }
        for d in case.documents
    ]


def get_timeline(case: Case) -> list[dict[str, Any]]:
    return [
        {"at": e.occurred_at.isoformat(), "actor": e.actor, "event": e.event_type, "description": e.description}
        for e in case.events[-15:]
    ]


def evaluate_case(case: Case) -> dict[str, Any]:
    verdict, explanation = adjudication_service.preview(case)
    return {**verdict.to_dict(), "explanation": explanation}


TOOLS: dict[str, tuple[Tool, str]] = {
    "get_case": (get_case, "Case facts: reason code, merchant, amount, status, deadline."),
    "get_evidence": (get_evidence, "Evidence items with status, source, model confidence and citation."),
    "get_documents": (get_documents, "Uploaded documents with type, OCR confidence and visual findings."),
    "get_timeline": (get_timeline, "Most recent audit timeline events."),
    "evaluate_case": (evaluate_case, "Run the deterministic rule engine on current evidence (read-only)."),
}


def openai_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": {"type": "object", "properties": {}}},
        }
        for name, (_, description) in TOOLS.items()
    ]


def call(name: str, case: Case) -> Any:
    if name not in TOOLS:
        raise KeyError(f"Unknown tool: {name}")
    return TOOLS[name][0](case)
