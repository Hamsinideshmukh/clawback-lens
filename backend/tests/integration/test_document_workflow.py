"""Upload -> queue -> vision pipeline -> extraction -> rule engine -> policy."""

import pytest
from fastapi.testclient import TestClient

from app.workflow import worker
from tests.integration.conftest import create_case


def upload(client: TestClient, case_id: str, content: bytes, content_type: str = "image/png", name: str = "a.png"):
    return client.post(f"/api/v1/cases/{case_id}/documents", files={"file": (name, content, content_type)})


@pytest.mark.slow
def test_scanned_receipt_resolves_the_dispute(client: TestClient, delivery_receipt_png: bytes) -> None:
    case = create_case(client, reason_code="4554")
    response = upload(client, case["id"], delivery_receipt_png)
    assert response.status_code == 202
    document_id = response.json()["id"]
    assert response.json()["status"] == "queued"

    assert worker.run_once() is True
    assert worker.run_once() is False  # queue drained

    document = client.get(f"/api/v1/documents/{document_id}").json()
    assert document["status"] == "completed"
    assert document["doc_type"] == "delivery_receipt"
    assert document["analysis"]["pages"][0]["signatures"]
    assert client.get(f"/api/v1/documents/{document_id}/preview").headers["content-type"] == "image/jpeg"

    detail = client.get(f"/api/v1/cases/{case['id']}").json()
    assert detail["transaction_type"] == "physical_goods"
    [evidence] = detail["evidence"]
    assert (evidence["key"], evidence["source"], evidence["document_id"]) == (
        "signed_delivery_receipt",
        "document",
        document_id,
    )
    assert "signed for by Aarav Singh" in evidence["citation"]
    assert (detail["status"], detail["outcome"]) == ("resolved", "merchant")


def test_duplicate_and_unsupported_uploads_are_rejected(client: TestClient) -> None:
    case = create_case(client)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    assert upload(client, case["id"], png).status_code == 202
    assert upload(client, case["id"], png).status_code == 409
    assert upload(client, case["id"], b"hello", "text/plain", "a.txt").status_code == 422
    assert upload(client, case["id"], b"", "image/png").status_code == 422


def test_corrupt_image_fails_the_document_without_retrying(client: TestClient) -> None:
    case = create_case(client)
    document_id = upload(client, case["id"], b"\x89PNG not really").json()["id"]
    assert worker.run_once()
    document = client.get(f"/api/v1/documents/{document_id}").json()
    assert document["status"] == "failed"
    assert "decode" in document["error"]
    assert worker.run_once() is False


def test_upload_answers_a_pending_retrieval_request(client: TestClient) -> None:
    case = create_case(client)
    assert client.post(f"/api/v1/cases/{case['id']}/retrieval-requests").status_code == 201
    upload(client, case["id"], b"\x89PNG not really")
    detail = client.get(f"/api/v1/cases/{case['id']}").json()
    assert detail["retrieval_requests"][0]["status"] == "fulfilled"
