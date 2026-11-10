"""Pipeline/product metrics for the dashboard's "freshness" panel."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifeops_core.models import Expense, IngestionRun, ManualDailyLog, RawSourceObject
from lifeops_core.repositories.ingestion_runs import IngestionRunRepository


class MetricsService:
    """One read-only snapshot for GET /api/v1/metrics.

    Deliberately derived from commit-day tables; once Gold tables exist this
    becomes a thin reader over marts instead of direct table scans.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def snapshot(self) -> dict:
        counts = {
            "manual_daily_logs": _count(self.session, ManualDailyLog),
            "expenses": _count(self.session, Expense),
            "ingestion_runs": _count(self.session, IngestionRun),
            "raw_source_objects": _count(self.session, RawSourceObject),
            "raw_source_objects_last_24h": _count_last_24h(self.session),
        }
        latest_runs = [
            {
                "source_name": source,
                "status": status,
                "started_at": started,
                "finished_at": finished,
            }
            for source, status, started, finished in IngestionRunRepository(
                self.session
            ).latest_per_source()
        ]
        return {
            "counts": [{"key": k, "value": v} for k, v in counts.items()],
            "latest_runs": latest_runs,
        }


def _count(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _count_last_24h(session: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    return int(
        session.scalar(
            select(func.count())
            .select_from(RawSourceObject)
            .where(RawSourceObject.ingested_at >= cutoff)
        )
        or 0
    )
