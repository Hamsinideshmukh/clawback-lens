"""FastAPI application factory."""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import cases, documents, meta
from app.core.config import get_settings
from app.core.errors import DomainError
from app.core.logging import configure_logging, request_id_var
from app.core.metrics import HTTP_LATENCY
from app.ml.models import get_models
from app.workflow import worker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    get_models()  # fail fast on a missing or tampered model artifact
    stop = None
    if settings.worker_embedded:
        _, stop = worker.start_in_thread()
    logger.info("api started", extra={"extra_fields": {"llm_enabled": settings.llm_enabled}})
    yield
    if stop:
        stop.set()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Clawback Lens API",
        description="Chargeback dispute resolution with computer-vision evidence extraction. "
        "AI proposes evidence; a deterministic rule engine decides.",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def observe(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        route = request.scope.get("route")
        HTTP_LATENCY.labels(request.method, getattr(route, "path", "unmatched"), response.status_code).observe(
            time.perf_counter() - start
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    app.include_router(meta.router)
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(documents.router, prefix="/api/v1")
    return app


app = create_app()
