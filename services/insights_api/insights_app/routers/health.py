"""Insights-service health check (same readiness contract as ingestion-api)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from lifeops_core.api import readiness_payload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/v1/health", name="health")
def health(request: Request) -> JSONResponse:
    factory = getattr(request.app.state, "session_factory", None)
    db_state = "down"
    if factory is not None:
        try:
            with factory() as session:
                session.execute(text("select 1"))
            db_state = "up"
        except Exception as exc:
            logger.warning("health: database down: %s", exc)

    object_store = getattr(request.app.state, "object_store", None)
    store_state = "down"
    if object_store is not None:
        try:
            store_state = "up" if object_store.bucket_exists() else "missing-bucket"
        except Exception as exc:
            logger.warning("health: minio down: %s", exc)

    code, payload = readiness_payload(
        service=request.app.state.service_name,
        version=getattr(request.app.state, "version", "unknown"),
        database=db_state,
        object_store=store_state,
    )
    payload["components"] = [
        {"name": "database", "status": db_state},
        {"name": "object_store", "status": store_state},
    ]
    return JSONResponse(status_code=code, content=payload)
