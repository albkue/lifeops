from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ingestion_app.deps import get_session
from ingestion_app.schemas import MetricsResponse
from ingestion_app.services.metrics import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/api/v1/metrics", name="app_metrics")
def app_metrics(
    request: Request,
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Operational + product metrics (counts + pipeline freshness)."""
    snapshot = MetricsService(session).snapshot()
    payload = MetricsResponse(
        service="ingestion-api",
        generated_at=datetime.now(UTC),
        counts=snapshot["counts"],
        latest_runs=snapshot["latest_runs"],
    )
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))
