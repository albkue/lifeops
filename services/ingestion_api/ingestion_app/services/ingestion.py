"""Ingestion orchestration service (the run-startup seam for Phase 6+)."""

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from lifeops_core.domain_errors import DomainValidationError
from lifeops_core.models import IngestionRun
from lifeops_core.models.enums import RunType
from lifeops_core.repositories.ingestion_runs import IngestionRunRepository
from lifeops_core.storage.bronze import BronzeStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    description: str
    planned_phase: str


# Single source of truth for what /ingestion/{source}/run accepts. Adapters
# register into ADAPTERS (lifeops_core.sources) when implemented.
KNOWN_SOURCES: dict[str, SourceSpec] = {
    spec.name: spec
    for spec in [
        SourceSpec("github", "Commits, PRs, repos, contribution activity", "Phase 6"),
        SourceSpec("calendar", "Google Calendar events + durations", "Phase 7"),
        SourceSpec("spotify", "Recently played tracks", "Phase 11"),
        SourceSpec("weather", "Daily temperature, rain, air quality", "Phase 11"),
        SourceSpec("expenses", "Manual/CSV expense ingestion", "Phase 11"),
    ]
}


class SourceAdapterMissingError(RuntimeError):
    """Raised when a known source has no implemented adapter yet."""


class IngestionService:
    """Start + bookkeep ingestion runs. Registered adapters land in Phase 6+."""

    def __init__(self, session: Session, storage: BronzeStorage | None) -> None:
        self.session = session
        self.storage = storage

    # ------------------------------------------------------------- runs list
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
        return IngestionRunRepository(self.session).list_runs(
            source_name=source_name,
            status=status,
            run_type=run_type,
            window_from=window_from,
            window_to=window_to,
            limit=limit,
            offset=offset,
        )

    # ------------------------------------------------................ run
    def run(
        self,
        *,
        source_name: str,
        run_type: RunType | str,
        window_start: datetime | None,
        window_end: datetime | None,
        trigger: str | None = None,
    ) -> IngestionRun:
        """Create a run and invoke its adapter.

        Adapters land incrementally (Phase 6 github, Phase 7 calendar, Phase 11
        spotify/weather/expenses). Until then a configured-but-missing adapter
        raises SourceAdapterMissingError, mapped to HTTP 501 by the router.
        """
        spec = KNOWN_SOURCES.get(source_name)
        if spec is None:
            raise DomainValidationError(
                f"unknown source '{source_name}'",
                details={"known_sources": sorted(KNOWN_SOURCES)},
            )
        if run_type == RunType.BACKFILL and (window_start is None or window_end is None):
            raise DomainValidationError("backfill requires window_start and window_end")
        if window_start and window_end and window_start > window_end:
            raise DomainValidationError("window_start must be <= window_end")

        from lifeops_core.sources.registry import get_adapter  # local import to avoid cycles

        adapter = get_adapter(source_name)
        if adapter is None:
            raise SourceAdapterMissingError(
                f"source '{source_name}' is registered but its adapter ships in "
                f"{spec.planned_phase}; no implementation yet."
            )

        run = IngestionRunRepository(self.session).create(
            user_id=None,  # adapter binds to the default user today
            source_name=source_name,
            run_type=run_type,
            window_start=window_start,
            window_end=window_end,
            trigger=trigger,
        )
        self.session.commit()
        try:
            adapter.run(run=run, session=self.session, storage=self.storage)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.exception("adapter for %s failed", source_name)
            IngestionRunRepository(self.session).mark_failed(run, str(exc))
            self.session.commit()
            raise
        return run
