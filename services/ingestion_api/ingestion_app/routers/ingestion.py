"""HTTP layer for ingestion runs (Phase 1: bookkeeping only, adapters come later)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ingestion_app.deps import get_current_user, get_session
from ingestion_app.schemas import (
    BronzeAuditReport,
    BronzeObjectPage,
    BronzeObjectRead,
    IngestionRunPage,
    IngestionRunRead,
    IngestionWindowRequest,
)
from ingestion_app.services.bronze_audit import BronzeIntrospectionService
from ingestion_app.services.ingestion import (
    KNOWN_SOURCES,
    IngestionService,
    SourceAdapterMissingError,
)
from lifeops_core.domain_errors import DomainValidationError
from lifeops_core.models import User

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


def build_service(request: Request, session: Session) -> IngestionService:
    return IngestionService(
        session=session,
        storage=request.app.state.bronze_storage,
    )


@router.post("/{source}/run", name="run_ingestion_source")
def run_ingestion_source(
    source: str,
    request: Request,
    window: IngestionWindowRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Trigger a one-off incremental run for `source`.

    Response codes:
    - 202 Accepted + run id: run started (sync execution in v1)
    - 422: unknown source / invalid window
    - 501: registered source with no adapter yet (feature scheduled later)
    """
    service = build_service(request, session)
    try:
        run = service.run(
            source_name=source,
            run_type="manual",
            window_start=window.window_start if window else None,
            window_end=window.window_end if window else None,
            trigger="api_manual_run",
        )
    except SourceAdapterMissingError as exc:
        return JSONResponse(
            status_code=501,
            content={"error": "Source Adapter Not Available", "message": str(exc)},
        )
    return JSONResponse(
        status_code=202,
        content={"run": IngestionRunRead.model_validate(run).model_dump(mode="json")},
    )


@router.post("/{source}/backfill", name="backfill_source")
def backfill_ingestion_source(
    source: str,
    window: IngestionWindowRequest,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> JSONResponse:
    """Re-run extraction over an explicit date window (idempotent)."""
    service = build_service(request, session)
    try:
        run = service.run(
            source_name=source,
            run_type="backfill",
            window_start=window.window_start,
            window_end=window.window_end,
            trigger="api_backfill",
        )
    except SourceAdapterMissingError as exc:
        return JSONResponse(
            status_code=501,
            content={"error": "Source Adapter Not Available", "message": str(exc)},
        )
    return JSONResponse(
        status_code=202,
        content={"run": IngestionRunRead.model_validate(run).model_dump(mode="json")},
    )


@router.get("/runs", response_model=IngestionRunPage, name="list_ingestion_runs")
def list_ingestion_runs(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    source_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    run_type: str | None = Query(default=None),
    window_from: datetime | None = Query(
        default=None, description="Runs whose window overlaps [window_from, window_to)"
    ),
    window_to: datetime | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IngestionRunPage:
    """Pipeline health inspection source (used by the dashboard)."""
    service = build_service(request, session)
    items, total = service.list_runs(
        source_name=source_name,
        status=status,
        run_type=run_type,
        window_from=window_from,
        window_to=window_to,
        limit=limit,
        offset=offset,
    )
    return IngestionRunPage(
        items=[IngestionRunRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sources", name="list_known_sources")
def list_known_sources() -> dict:
    """Discovery endpoint: what /run knows about, and which are live yet."""
    return {
        "sources": [
            {
                "name": spec.name,
                "description": spec.description,
                "planned_phase": spec.planned_phase,
                "adapter_available": spec.name in _available(),
            }
            for spec in KNOWN_SOURCES.values()
        ]
    }


def _available() -> set[str]:
    from lifeops_core.sources.registry import available_sources

    return set(available_sources().keys())


# ---------------------------------------------------------------------------
# Phase 2: Bronze introspection (catalog + integrity audit)
# ---------------------------------------------------------------------------


def _build_introspection(request: Request, session: Session) -> BronzeIntrospectionService:
    return BronzeIntrospectionService(
        session=session,
        session_factory=request.app.state.session_factory,
        store=request.app.state.object_store,
    )


@router.get("/objects", response_model=BronzeObjectPage, name="list_bronze_objects")
def list_bronze_objects(
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    source_name: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    window_from: datetime | None = Query(default=None),
    window_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> BronzeObjectPage:
    """Paginated Bronze ledger catalog — the raw-quarter data catalog for the dashboard."""
    service = _build_introspection(request, session)
    items, total = service.list_objects(
        source_name=source_name,
        dataset=dataset,
        window_from=window_from,
        window_to=window_to,
        limit=limit,
        offset=offset,
    )
    return BronzeObjectPage(
        items=[BronzeObjectRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{source}/audit", response_model=BronzeAuditReport, name="audit_bronze_source")
def audit_bronze_source(
    source: str,
    request: Request,
    window: IngestionWindowRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    dataset: str | None = Query(default=None),
    problem_limit: int = Query(default=200, ge=1, le=1000),
) -> BronzeAuditReport:
    """Integrity audit: every ledger row must exist in the store and re-hash
    to its ledger digest. Read-only detection — repair arrives with the
    extractors only, Phase 6+, since they hold the second data copy)."""
    if source not in KNOWN_SOURCES:
        raise DomainValidationError(
            f"unknown source '{source}'", details={"known_sources": sorted(KNOWN_SOURCES)}
        )
    service = _build_introspection(request, session)
    window_from = window.window_start if window else None
    window_to = window.window_end if window else None
    report = service.audit_source(
        source_name=source,
        dataset=dataset,
        window_from=window_from,
        window_to=window_to,
        max_problems=problem_limit,
    )
    return BronzeAuditReport.model_validate(
        {
            "source_name": report.source_name,
            "dataset": report.dataset,
            "checked_at": report.checked_at,
            "ledger_rows": report.ledger_rows,
            "ok": report.ok,
            "missing": report.missing,
            "corrupt": report.corrupt,
            "truncated": report.truncated,
            "problems": [
                {
                    "object_key": p.object_key,
                    "payload_sha256": p.payload_sha256,
                    "problem": p.problem,
                    "detail": p.detail,
                }
                for p in report.problems
            ],
        }
    )
