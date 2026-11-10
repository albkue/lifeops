import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifeops_core.models import IngestionError, IngestionRun
from lifeops_core.models.enums import ErrorStage, IngestionStatus, RunType


class IngestionRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        user_id: uuid.UUID | None,
        source_name: str,
        run_type: RunType | str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        trigger: str | None = None,
        started_at: datetime | None = None,
    ) -> IngestionRun:
        run = IngestionRun(
            user_id=user_id,
            source_name=source_name,
            run_type=str(run_type),
            status=IngestionStatus.RUNNING.value,
            started_at=started_at or datetime.now(UTC),
            window_start=window_start,
            window_end=window_end,
            trigger=trigger,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def mark_success(
        self,
        run: IngestionRun,
        *,
        records_extracted: int = 0,
        records_loaded: int = 0,
        error_count: int = 0,
        run_metadata: dict | None = None,
        finished_at: datetime | None = None,
    ) -> IngestionRun:
        run.status = IngestionStatus.SUCCESS.value
        run.finished_at = finished_at or datetime.now(UTC)
        run.records_extracted = records_extracted
        run.records_loaded = records_loaded
        run.error_count = error_count
        if run_metadata is not None:
            run.run_metadata = run_metadata
        self.session.flush()
        return run

    def mark_failed(self, run: IngestionRun, message: str) -> IngestionRun:
        run.status = IngestionStatus.FAILED.value
        run.finished_at = datetime.now(UTC)
        run.error_message = message
        self.session.flush()
        return run

    def list_runs(
        self,
        *,
        source_name: str | None = None,
        status: str | None = None,
        run_type: str | None = None,
        window_from: datetime | None = None,
        window_to: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[IngestionRun], int]:
        """List runs; window_from/window_to use OVERLAP semantics: a run counts
        when its extraction window intersects [window_from, window_to). Runs
        without a window never match a window filter."""
        base = select(IngestionRun)
        if source_name:
            base = base.where(IngestionRun.source_name == source_name)
        if status:
            base = base.where(IngestionRun.status == status)
        if run_type:
            base = base.where(IngestionRun.run_type == run_type)
        # Window overlap filters: windowless runs intentionally NEVER match a
        # window query (documented semantics) â€” NULL comparisons fail naturally.
        if window_from is not None:
            base = base.where(IngestionRun.window_end > window_from)
        if window_to is not None:
            base = base.where(IngestionRun.window_start < window_to)

        total = self.session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
        rows = (
            self.session.execute(
                base.order_by(IngestionRun.started_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    def latest_per_source(self) -> list[tuple[str, str, datetime, datetime | None]]:
        """Deduplicated latest run per source for freshness dashboards."""
        latest_sub = select(
            IngestionRun.source_name,
            IngestionRun.started_at,
            IngestionRun.status,
            IngestionRun.finished_at,
            func.row_number()
            .over(partition_by=IngestionRun.source_name, order_by=IngestionRun.started_at.desc())
            .label("rn"),
        ).subquery()
        stmt = (
            select(
                latest_sub.c.source_name,
                latest_sub.c.status,
                latest_sub.c.started_at,
                latest_sub.c.finished_at,
            )
            .where(latest_sub.c.rn == 1)
            .order_by(latest_sub.c.source_name)
        )
        return [
            (r.source_name, r.status, r.started_at, r.finished_at)
            for r in self.session.execute(stmt)
        ]


class IngestionErrorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        ingestion_run_id: uuid.UUID,
        source_name: str,
        stage: ErrorStage | str,
        message: str,
        detail: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> IngestionError:
        row = IngestionError(
            ingestion_run_id=ingestion_run_id,
            source_name=source_name,
            stage=str(stage),
            message=message,
            detail=detail or {},
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self.session.add(row)
        self.session.flush()
        return row
