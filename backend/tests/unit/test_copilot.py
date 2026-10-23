from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.agents import supervisor
from app.agents.planner import DEFAULT_PLAN, plan_for_message
from app.ai import llm
from app.db.models import Case, Evidence


def make_case() -> Case:
    case = Case(
        id="c1",
        transaction_id="t1",
        merchant_name="Orbit Retail",
        amount=Decimal("10.00"),
        currency="USD",
        reason_code="4530",
        status="open",
        respond_by=datetime(2026, 11, 1, tzinfo=UTC),
    )
    case.evidence = [
        Evidence(
            key="correcting_transaction_processed",
            status="satisfied",
            source="document",
            confidence=0.93,
            citation="Refund processed",
        )
    ]
    case.documents, case.events = [], []
    return case


def test_planner_routes_intents() -> None:
    assert plan_for_message("Why did I lose?") == ["get_case", "evaluate_case", "get_evidence"]
    assert plan_for_message("what is the deadline") == ["get_case", "get_timeline"]
    assert plan_for_message("hello") == DEFAULT_PLAN


def test_deterministic_copilot_answers_from_rule_engine_facts() -> None:
    response = supervisor.handle_chat(make_case(), "why?")
    assert response.mode == "deterministic"
    assert "resolved in the merchant's favor" in response.reply
    assert "correcting transaction processed (93%)" in response.reply


def test_llm_copilot_runs_a_tool_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = iter(
        [
            {"content": None, "tool_calls": [{"id": "1", "function": {"name": "evaluate_case", "arguments": "{}"}}]},
            {"content": "The refund satisfies RC 4530, so the merchant wins."},
        ]
    )
    seen: list[list[dict[str, Any]]] = []

    def fake_chat(messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        seen.append(list(messages))
        return next(replies)

    monkeypatch.setattr(llm, "chat", fake_chat)
    response = supervisor.handle_chat(make_case(), "why?")
    assert response.mode == "llm"
    assert response.tools_used == ["evaluate_case"]
    assert seen[1][-1]["role"] == "tool"
    assert "auto_resolve_merchant" in seen[1][-1]["content"]
