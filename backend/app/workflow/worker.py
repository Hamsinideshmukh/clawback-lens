"""Background worker: drains the job queue and runs the periodic SLA sweep.

Runs as its own process (`python -m app.workflow.worker`, the `worker`
service in docker-compose) or as a thread inside the API process when
WORKER_EMBEDDED=true, which keeps single-container free-tier hosting simple."""

import logging
import signal
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging, log_extra
from app.core.metrics import JOBS
from app.db.session import SessionLocal, session_scope
from app.services import document_service, sla_service
from app.workflow import queue

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict[str, Any]], None]
ExhaustedHook = Callable[[Session, dict[str, Any], str], None]

HANDLERS: dict[str, tuple[Handler, ExhaustedHook | None]] = {
    document_service.PROCESS_DOCUMENT: (document_service.process, document_service.on_exhausted),
}
STALE_AFTER = timedelta(minutes=10)


def run_once() -> bool:
    """Processes at most one job. Returns False when the queue is empty."""
    with SessionLocal() as db:
        job = queue.claim(db)
        if job is None:
            return False
        job_id, kind, payload = job.id, job.kind, dict(job.payload)

    handler, on_exhausted = HANDLERS[kind]
    started = time.perf_counter()
    try:
        with session_scope() as db:
            handler(db, payload)
            queue.complete(db, job_id)
        JOBS.labels(kind, "done").inc()
        logger.info(
            "job done", extra=log_extra(job_id=job_id, kind=kind, ms=round((time.perf_counter() - started) * 1000))
        )
    except Exception as exc:
        logger.exception("job failed", extra=log_extra(job_id=job_id, kind=kind))
        with session_scope() as db:
            exhausted = queue.fail(db, job_id, repr(exc), get_settings().job_max_attempts)
            if exhausted and on_exhausted:
                on_exhausted(db, payload, repr(exc))
        JOBS.labels(kind, "exhausted" if exhausted else "retry").inc()
    return True


def run_maintenance() -> None:
    with session_scope() as db:
        requeued = queue.requeue_stale(db, STALE_AFTER)
        summary = sla_service.sweep(db)
    if requeued or any(summary.values()):
        logger.info("maintenance", extra=log_extra(requeued=requeued, **summary))


def run_forever(stop: threading.Event) -> None:
    settings = get_settings()
    next_maintenance = 0.0
    logger.info("worker started")
    while not stop.is_set():
        try:
            if time.monotonic() >= next_maintenance:
                run_maintenance()
                next_maintenance = time.monotonic() + settings.sla_sweep_seconds
            if not run_once():
                stop.wait(settings.worker_poll_seconds)
        except Exception:  # database blip: log, back off, keep the worker alive
            logger.exception("worker loop error")
            stop.wait(5)
    logger.info("worker stopped")


def start_in_thread() -> tuple[threading.Thread, threading.Event]:
    stop = threading.Event()
    thread = threading.Thread(target=run_forever, args=(stop,), name="job-worker", daemon=True)
    thread.start()
    return thread, stop


def main() -> None:
    configure_logging(get_settings().log_level)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    run_forever(stop)


if __name__ == "__main__":
    main()
