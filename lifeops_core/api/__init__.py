"""Shared FastAPI plumbing: error mapping, health, dependency stubs.

Kept here so the ingestion and insights services implement the HTTP contract
exactly once (route handlers stay thin wrappers over services).
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from lifeops_core.config import Settings
from lifeops_core.domain_errors import DomainError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI, service: str) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.title,
                "message": exc.message,
                "details": exc.details,
                "service": service,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Failed",
                "message": "Request body/query failed schema validation.",
                "details": [
                    {"loc": [str(p) for p in err["loc"]], "msg": err["msg"]} for err in exc.errors()
                ],
                "service": service,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error in %s: %s", service, exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Error", "message": str(exc), "service": service},
        )


def build_app(
    *,
    settings: Settings,
    title: str,
    version: str,
    service: str,
    router_includes: list[Callable[[], None]] | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    """Two services share one construction path so OpenAPI stays consistent."""
    app = FastAPI(
        title=title,
        version=version,
        description=(
            "LifeOps — Personal Data Lakehouse. Local-first API for habits, "
            "health, coding, calendar, music, spending and pipeline health."
        ),
        lifespan=lifespan,
    )
    if router_includes:
        for include in router_includes:
            include()
    app.state.settings = settings
    app.state.service_name = service
    register_error_handlers(app, service=service)
    return app


def readiness_payload(
    *,
    service: str,
    version: str,
    database: str,
    object_store: str = "unknown",
) -> tuple[int, dict]:
    """Consistent /health payload shape across services.

    HTTP semantics: 503 only when a REQUIRED dependency (Postgres) is down.
    MinIO being down degrades the service ('degraded', 200) because the API
    can still serve reads/writes that don't touch Bronze.
    """
    if database == "down":
        code = 503
        overall = "unavailable"
    elif object_store == "down":
        code = 200
        overall = "degraded"
    else:
        code = 200
        overall = "ok"
    return code, {
        "status": overall,
        "service": service,
        "components": {"database": database, "object_store": object_store},
        "version": version,
    }
