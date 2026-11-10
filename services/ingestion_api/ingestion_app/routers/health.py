import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from lifeops_core.api import readiness_payload
from lifeops_core.storage.object_store import MinioObjectStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


def _check_database(session_factory: sessionmaker[Session] | None) -> str:
    if session_factory is None:
        return "down"
    try:
        with session_factory() as session:
            session.execute(text("select 1"))
    except Exception as exc:
        logger.warning("health: database down: %s", exc)
        return "down"
    return "up"


def _check_object_store(object_store: MinioObjectStore | None) -> str:
    if object_store is None:
        return "down"
    try:
        return "up" if object_store.bucket_exists() else "missing-bucket"
    except Exception as exc:
        logger.warning("health: minio down: %s", exc)
        return "down"


@router.get("/api/v1/health", name="health")
def health(request: Request) -> JSONResponse:
    """DB is critical (503 when down); Bronze storage is best-effort (200 degraded)."""
    db_state = _check_database(getattr(request.app.state, "session_factory", None))
    store_state = _check_object_store(getattr(request.app.state, "object_store", None))

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
