"""Thin HTTP layer: /api/v1/logs/daily CRUD.

Handlers only:
- bind typed inputs/outputs
- delegate to DailyLogService (business rules)
- map service outcomes to HTTP codes
No business logic lives here.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ingestion_app.deps import get_current_user, get_session
from ingestion_app.schemas import DailyLogPage, DailyLogUpsertResult
from ingestion_app.services.manual_logs import BronzeOutcome, DailyLogService
from lifeops_core.models import User
from lifeops_core.schemas import BronzeRef, DailyLogCreate, DailyLogRead, DailyLogUpdate

router = APIRouter(prefix="/api/v1/logs", tags=["manual-logs"])


def build_service(request: Request, session: Session) -> DailyLogService:
    """Services resolve from app.state so swapping engines (tests) is trivial."""
    return DailyLogService(
        session=session,
        storage=request.app.state.bronze_storage,
        settings=request.app.state.settings,
        clock=request.app.state.clock,
    )


@router.post("/daily", name="upsert_daily_log", response_model=DailyLogUpsertResult)
def upsert_daily_log(
    payload: DailyLogCreate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Create (or fill-in) the day's log.

    Upsert semantics: if a record for (user, log_date) already exists, only
    provided fields are merged (remaining fields untouched), so a
    mobile-quick-entry flow can safely re-submit.
    """
    service = build_service(request, session)
    row, created, bronze = service.upsert_daily_log(user, payload)
    result = DailyLogUpsertResult(
        record=DailyLogRead.model_validate(row), created=created, bronze=_bronze_ref(bronze)
    )
    return JSONResponse(status_code=201 if created else 200, content=result.model_dump(mode="json"))


@router.patch("/daily/{log_id}", name="patch_daily_log", response_model=DailyLogRead)
def patch_daily_log(
    log_id: uuid.UUID,
    payload: DailyLogUpdate,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Explicit field override; set a field to update it; absent fields no-op."""
    service = build_service(request, session)
    row, _ = service.update_daily_log(user, log_id, payload)
    return JSONResponse(
        status_code=200, content=DailyLogRead.model_validate(row).model_dump(mode="json")
    )


@router.delete("/daily/{log_id}", status_code=204, name="delete_daily_log")
def delete_daily_log(
    log_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    service = build_service(request, session)
    service.delete_daily_log(user, log_id)
    return Response(status_code=204)


@router.get("/daily", response_model=DailyLogPage, name="list_daily_logs")
def list_daily_logs(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    start_date: date | None = Query(default=None, description="Inclusive lower bound"),
    end_date: date | None = Query(default=None, description="Inclusive upper bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DailyLogPage:
    """Paginated daily-log range query, newest dates first."""
    service = build_service(request, session)
    items, total = service.list_range(
        user, start_date=start_date, end_date=end_date, limit=limit, offset=offset
    )
    return DailyLogPage(
        items=[DailyLogRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/daily/by-date/{log_date}", name="get_daily_log_by_date", response_model=DailyLogRead)
def get_daily_log_by_date(
    log_date: date,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Fetch a single day's log; 404 JSON body if nothing is tracked yet."""
    service = build_service(request, session)
    row = service.get_by_date(user, log_date)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Not Found", "message": f"No daily log for {log_date}."},
        )
    return JSONResponse(
        status_code=200, content=DailyLogRead.model_validate(row).model_dump(mode="json")
    )


def _bronze_ref(outcome: BronzeOutcome | None) -> BronzeRef | None:
    if outcome is None or outcome.object_key is None:
        return None
    return BronzeRef(
        object_key=outcome.object_key,
        sha256=outcome.sha256 or "",
        size_bytes=outcome.size_bytes or 0,
        deduplicated=outcome.deduplicated,
    )
