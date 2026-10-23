"""A durable job queue on PostgreSQL.

`claim()` uses `SELECT ... FOR UPDATE SKIP LOCKED`, the standard Postgres
queue pattern: concurrent workers each lock a different row and never block
one another, so the queue scales out by starting more worker processes
without adding Redis or a broker. Failed jobs retry with exponential backoff;
jobs whose worker died mid-run are re-queued by `requeue_stale()`."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, utcnow

BACKOFF_BASE_SECONDS = 5


def enqueue(db: Session, kind: str, payload: dict[str, Any], run_after: datetime | None = None) -> Job:
    job = Job(kind=kind, payload=payload, status=JobStatus.QUEUED, run_after=run_after or utcnow())
    db.add(job)
    db.flush()
    return job


def claim(db: Session) -> Job | None:
    """Atomically takes the oldest runnable job. Commits so the lock is short."""
    job = db.scalars(
        select(Job)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= utcnow())
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        db.rollback()
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.locked_at = utcnow()
    db.commit()
    return job


def complete(db: Session, job_id: str) -> None:
    db.execute(update(Job).where(Job.id == job_id).values(status=JobStatus.DONE, locked_at=None, last_error=None))


def fail(db: Session, job_id: str, error: str, max_attempts: int) -> bool:
    """Schedules a retry, or marks the job failed. Returns True if exhausted."""
    job = db.get(Job, job_id)
    if job is None:
        return True
    job.last_error = error[:2000]
    job.locked_at = None
    if job.attempts >= max_attempts:
        job.status = JobStatus.FAILED
        return True
    job.status = JobStatus.QUEUED
    job.run_after = utcnow() + timedelta(seconds=BACKOFF_BASE_SECONDS * 2 ** (job.attempts - 1))
    return False


def requeue_stale(db: Session, older_than: timedelta) -> int:
    """Returns crashed workers' jobs to the queue."""
    result = db.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING, Job.locked_at < utcnow() - older_than)
        .values(status=JobStatus.QUEUED, locked_at=None)
    )
    return int(getattr(result, "rowcount", 0) or 0)
