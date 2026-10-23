from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Job, JobStatus, utcnow
from app.db.session import SessionLocal, session_scope
from app.services import sla_service
from app.workflow import queue
from tests.integration.conftest import create_case


def test_concurrent_workers_claim_different_jobs() -> None:
    with session_scope() as db:
        queue.enqueue(db, "noop", {"n": 1})
        queue.enqueue(db, "noop", {"n": 2})

    first, second = SessionLocal(), SessionLocal()
    try:
        # Hold the first claim's row lock open while the second worker claims.
        job_a = first.scalars(
            select(Job).where(Job.status == JobStatus.QUEUED).with_for_update(skip_locked=True).limit(1)
        ).first()
        job_b = queue.claim(second)
        assert job_a is not None
        assert job_b is not None
        assert job_a.id != job_b.id
        assert queue.claim(second) is None  # the only other row is locked by worker A
    finally:
        first.rollback()
        first.close()
        second.close()


def test_failed_jobs_back_off_then_exhaust() -> None:
    with session_scope() as db:
        job_id = queue.enqueue(db, "noop", {}).id
    for attempt in (1, 2, 3):
        with SessionLocal() as db:
            claimed = queue.claim(db)
            assert claimed is not None
            assert claimed.attempts == attempt
        with session_scope() as db:
            exhausted = queue.fail(db, job_id, "boom", max_attempts=3)
            job = db.get_one(Job, job_id)
            if attempt < 3:
                assert not exhausted
                assert job.run_after > utcnow()
                job.run_after = utcnow()  # skip the backoff wait
            else:
                assert exhausted
                assert job.status == JobStatus.FAILED


def test_stale_running_jobs_are_requeued() -> None:
    with session_scope() as db:
        job = queue.enqueue(db, "noop", {})
        job.status, job.locked_at = JobStatus.RUNNING, utcnow() - timedelta(hours=1)
    with session_scope() as db:
        assert queue.requeue_stale(db, timedelta(minutes=10)) == 1


def test_missed_retrieval_request_escalates_to_rc_4516(client: TestClient) -> None:
    case = create_case(client)
    client.post(f"/api/v1/cases/{case['id']}/retrieval-requests")
    with session_scope() as db:
        summary = sla_service.sweep(db, now=utcnow() + timedelta(days=11))
    assert summary["retrieval_requests_breached"] == 1
    detail = client.get(f"/api/v1/cases/{case['id']}").json()
    assert detail["reason_code"] == "4516"
    assert detail["retrieval_requests"][0]["status"] == "unfulfilled"


def test_expired_response_window_resolves_for_card_member(client: TestClient) -> None:
    open_case = create_case(client)
    escalated = create_case(client, reason_code="4553")
    client.put(f"/api/v1/cases/{escalated['id']}/evidence/description_match_proof", json={"status": "satisfied"})

    with session_scope() as db:
        assert sla_service.sweep(db, now=utcnow() + timedelta(days=30))["cases_expired"] == 1

    expired = client.get(f"/api/v1/cases/{open_case['id']}").json()
    assert (expired["status"], expired["outcome"]) == ("resolved", "card_member")
    assert client.get(f"/api/v1/cases/{escalated['id']}").json()["status"] == "escalated"
