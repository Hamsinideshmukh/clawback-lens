from fastapi.testclient import TestClient

from tests.integration.conftest import create_case


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/health/ready").json()
    assert ready["status"] == "ready"
    assert ready["llm_enabled"] is False
    assert "clawback_http_request_seconds" in client.get("/metrics").text


def test_reason_code_catalog(client: TestClient) -> None:
    codes = {c["reason_code"]: c for c in client.get("/api/v1/reason-codes").json()}
    assert codes["4554"]["transaction_types"] == ["physical_goods", "digital_goods", "travel"]
    assert codes["4553"]["always_escalate"] is True


def test_create_and_list_cases(client: TestClient) -> None:
    case = create_case(client)
    assert case["status"] == "open"
    assert case["reason_name"] == "Currency Discrepancy"
    assert case["required_evidence"] == ["correcting_transaction_processed", "chargeback_raised_in_error"]

    listing = client.get("/api/v1/cases").json()
    assert listing["total"] == 1
    assert listing["status_counts"] == {"open": 1}
    assert client.get("/api/v1/cases", params={"status": "resolved"}).json()["total"] == 0


def test_validation_errors(client: TestClient) -> None:
    bad = {"transaction_id": "t", "merchant_name": "m", "amount": "5", "reason_code": "9999"}
    assert client.post("/api/v1/cases", json=bad).status_code == 422
    assert client.post("/api/v1/cases", json={**bad, "reason_code": "4530", "amount": "-1"}).status_code == 422
    wrong_branch = {**bad, "reason_code": "4530", "transaction_type": "travel"}
    assert client.post("/api/v1/cases", json=wrong_branch).status_code == 422
    assert client.get("/api/v1/cases/nope").status_code == 404


def test_manual_evidence_auto_resolves_for_merchant(client: TestClient) -> None:
    case = create_case(client)
    response = client.put(
        f"/api/v1/cases/{case['id']}/evidence/correcting_transaction_processed", json={"status": "satisfied"}
    )
    body = response.json()
    assert body["status"] == "resolved"
    assert body["outcome"] == "merchant"
    assert body["latest_evaluation"]["status"] == "auto_resolve_merchant"

    # Resolved cases are immutable.
    again = client.put(f"/api/v1/cases/{case['id']}/evidence/chargeback_raised_in_error", json={"status": "satisfied"})
    assert again.status_code == 409


def test_unknown_evidence_key_is_rejected(client: TestClient) -> None:
    case = create_case(client)
    response = client.put(f"/api/v1/cases/{case['id']}/evidence/boarding_pass_scan", json={"status": "satisfied"})
    assert response.status_code == 422


def test_judgment_heavy_case_escalates_then_analyst_decides(client: TestClient) -> None:
    case = create_case(client, reason_code="4553")
    body = client.put(
        f"/api/v1/cases/{case['id']}/evidence/description_match_proof", json={"status": "satisfied"}
    ).json()
    assert body["status"] == "escalated"

    decided = client.post(
        f"/api/v1/cases/{case['id']}/decision", json={"outcome": "card_member", "note": "Photos show visible damage"}
    ).json()
    assert (decided["status"], decided["outcome"]) == ("resolved", "card_member")
    assert client.post(f"/api/v1/cases/{case['id']}/decision", json={"outcome": "merchant"}).status_code == 409

    timeline = client.get(f"/api/v1/cases/{case['id']}/timeline").json()
    assert [e["event_type"] for e in timeline] == [
        "case_opened",
        "evidence_updated",
        "verdict_issued",
        "case_escalated",
        "case_resolved",
    ]
    assert "Photos show visible damage" in timeline[-1]["description"]


def test_copilot_works_without_an_llm(client: TestClient) -> None:
    case = create_case(client)
    response = client.post(f"/api/v1/cases/{case['id']}/copilot", json={"message": "What evidence is missing?"})
    body = response.json()
    assert body["mode"] == "deterministic"
    assert "correcting transaction processed" in body["reply"]


def test_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/health", headers={"x-request-id": "abc123"})
    assert response.headers["x-request-id"] == "abc123"
