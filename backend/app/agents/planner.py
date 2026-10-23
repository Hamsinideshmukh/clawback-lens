"""Deterministic intent planner used when no LLM is configured: maps a
question to an ordered list of tools. Small, known intents do not need a
model to be answered reliably."""

_INTENTS: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("why", "lost", "lose", "reject", "explain", "verdict", "decision"),
        ["get_case", "evaluate_case", "get_evidence"],
    ),
    (("document", "upload", "ocr", "scan", "signature", "file"), ["get_documents", "get_evidence"]),
    (("missing", "need", "require", "what evidence"), ["get_case", "evaluate_case"]),
    (("status", "where", "stage", "progress", "deadline", "history"), ["get_case", "get_timeline"]),
]
DEFAULT_PLAN = ["get_case", "evaluate_case", "get_documents"]


def plan_for_message(message: str) -> list[str]:
    text = message.lower()
    for keywords, plan in _INTENTS:
        if any(k in text for k in keywords):
            return plan
    return DEFAULT_PLAN
