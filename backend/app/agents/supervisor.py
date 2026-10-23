"""Case copilot. With an LLM configured it runs a tool-calling loop over the
read-only tools in `tools.py`; without one (or if the call fails) it falls
back to the deterministic planner and a templated answer built from the same
tool results. Either way the facts come from the rule engine and case
records — the model only chooses which to fetch and how to phrase them."""

import json
import logging
from typing import Any

from app.agents import tools
from app.agents.planner import plan_for_message
from app.ai import llm
from app.db.models import Case
from app.schemas.case import ChatResponse

logger = logging.getLogger(__name__)
MAX_STEPS = 4
SYSTEM_PROMPT = (
    "You are a dispute-resolution copilot for card-network chargeback analysts. Use the tools to look up "
    "facts before answering. Never invent evidence and never contradict the rule engine's verdict; if "
    "something is unknown, say so. Answer in at most 4 sentences."
)


def handle_chat(case: Case, message: str) -> ChatResponse:
    try:
        return _llm_chat(case, message)
    except llm.LLMUnavailable:
        return _deterministic_chat(case, message)


def _llm_chat(case: Case, message: str) -> ChatResponse:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Case {case.id}: {message}"},
    ]
    used: list[str] = []
    for _ in range(MAX_STEPS):
        reply = llm.chat(messages, purpose="copilot", tools=tools.openai_tool_specs())
        calls = reply.get("tool_calls") or []
        if not calls:
            return ChatResponse(reply=(reply.get("content") or "").strip(), tools_used=used, mode="llm")
        messages.append({"role": "assistant", "content": reply.get("content"), "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            try:
                result: Any = tools.call(name, case)
                used.append(name)
            except KeyError as exc:
                result = {"error": str(exc)}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, default=str)})
    raise llm.LLMUnavailable("copilot exceeded its tool-call budget")


def _deterministic_chat(case: Case, message: str) -> ChatResponse:
    plan = plan_for_message(message)
    results = {name: tools.call(name, case) for name in plan}
    return ChatResponse(reply=_template_reply(results), tools_used=plan, mode="deterministic")


def _template_reply(results: dict[str, Any]) -> str:
    parts = []
    if case := results.get("get_case"):
        parts.append(f"Case under RC {case['reason_code']} against {case['merchant']} is {case['status']}.")
    if verdict := results.get("evaluate_case"):
        parts.append(verdict["explanation"])
    if documents := results.get("get_documents"):
        done = [d for d in documents if d["doc_type"]]
        if done:
            described = ", ".join(f"{d['filename']} ({d['doc_type'].replace('_', ' ')})" for d in done)
            parts.append(f"Analysed documents: {described}.")
        else:
            parts.append(f"{len(documents)} document(s) uploaded, none analysed yet.")
    if evidence := results.get("get_evidence"):
        from_docs = [e for e in evidence if e["source"] == "document" and e["status"] == "satisfied"]
        if from_docs:
            parts.append(
                "Evidence read from documents: "
                + "; ".join(f"{e['key'].replace('_', ' ')} ({e['confidence']:.0%})" for e in from_docs)
                + "."
            )
    if timeline := results.get("get_timeline"):
        parts.append(f"Latest event: {timeline[-1]['description']}")
    return " ".join(parts) or "I don't have enough information about this case yet."
