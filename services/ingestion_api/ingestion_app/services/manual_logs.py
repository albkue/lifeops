"""Business layer for manual daily logs. Route handlers call these only."""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from lifeops_core.config import Settings
from lifeops_core.domain_errors import DomainValidationError, NotFoundError
from lifeops_core.models import ManualDailyLog, User
from lifeops_core.repositories.manual_daily_logs import ManualDailyLogRepository
from lifeops_core.schemas import DailyLogCreate, DailyLogUpdate
from lifeops_core.storage.bronze import BronzeStorage
from lifeops_core.timeutils import ReportingClock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BronzeOutcome:
    object_key: str | None
    sha256: str | None
    size_bytes: int | None
    deduplicated: bool


class DailyLogService:
    """Manual daily habit log: API semantics + Bronze raw-event mirroring.

    POST is *upsert by (user_id, log_date)* so a phone-quick entry never 409s;
    PATCH provides explicit field overrides when you want to CLEAR a value.
    """

    def __init__(
        self,
        session: Session,
        storage: BronzeStorage,
        settings: Settings,
        clock: ReportingClock,
    ) -> None:
        self.session = session
        self.storage = storage
        self.settings = settings
        self.clock = clock

    # ------------------------------------------------------------------ write
    def upsert_daily_log(
        self, user: User, data: DailyLogCreate
    ) -> tuple[ManualDailyLog, bool, BronzeOutcome | None]:
        self._guard_too_far_future(data.log_date)
        repo = ManualDailyLogRepository(self.session)
        row, created = repo.upsert(user.id, data)
        self.session.commit()
        bronze = self._mirror_to_bronze(user, row, event="upsert")
        return row, created, bronze

    def update_daily_log(
        self, user: User, log_id: uuid.UUID, data: DailyLogUpdate
    ) -> tuple[ManualDailyLog, BronzeOutcome | None]:
        repo = ManualDailyLogRepository(self.session)
        row = repo.get(user.id, log_id)
        if row is None:
            raise NotFoundError(f"daily log {log_id} not found")
        repo.apply_update(row, data)
        self.session.commit()
        bronze = self._mirror_to_bronze(user, row, event="patch_update")
        return row, bronze

    def delete_daily_log(self, user: User, log_id: uuid.UUID) -> None:
        repo = ManualDailyLogRepository(self.session)
        row = repo.get(user.id, log_id)
        if row is None:
            raise NotFoundError(f"daily log {log_id} not found")
        repo.delete(row)
        self.session.commit()

    # ------------------------------------------------------------------- read
    def get_by_date(self, user: User, log_date: date) -> ManualDailyLog | None:
        return ManualDailyLogRepository(self.session).get_by_date(user.id, log_date)

    def list_range(
        self,
        user: User,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ManualDailyLog], int]:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise DomainValidationError("start_date must be <= end_date")
        return ManualDailyLogRepository(self.session).list_range(
            user.id, start_date=start_date, end_date=end_date, limit=limit, offset=offset
        )

    # ---------------------------------------------------------------- helpers
    def _guard_too_far_future(self, log_date: date) -> None:
        """Allow `today` and `tomorrow` (midnight rollover safety), nothing later."""
        max_allowed = self.clock.today() + timedelta(days=1)
        if log_date > max_allowed:
            raise DomainValidationError(
                "log_date is too far in the future (max tomorrow)",
                details={"log_date": str(log_date), "max_allowed": str(max_allowed)},
            )

    def _mirror_to_bronze(
        self, user: User, row: ManualDailyLog, *, event: str
    ) -> BronzeOutcome | None:
        """Mirror the committed record into Bronze as a raw source event.

        Best effort BY DESIGN: a MinIO hiccup must not break manual logging.
        The warehouse row is already committed; Bronze evidence catches up via
        the next daily backfill. Failures are logged, never raised.
        """
        payload = {
            "record_id": str(row.id),
            "user_id": str(row.user_id),
            "log_date": row.log_date.isoformat(),
            "sleep_hours": _num(row.sleep_hours),
            "mood_score": row.mood_score,
            "study_hours": _num(row.study_hours),
            "coding_hours": _num(row.coding_hours),
            "workout_minutes": row.workout_minutes,
            "soccer_minutes": row.soccer_minutes,
            "notes": row.notes,
            "tags": list(row.tags or []),
        }
        payload_json = {"payload": payload, "_lifeops_event_kind": event}
        window_start, window_end = self.clock.local_day_bounds_utc(row.log_date)
        try:
            outcome = self.storage.write(
                source_name="manual_logs",
                dataset="daily_logs",
                payload=payload_json,
                user_id=user.id,
                window_start=window_start,
                window_end=window_end,
                attributes={"record_id": str(row.id), "event": event},
            )
        except Exception as exc:
            logger.warning("Bronze mirror failed for log_date=%s: %s", row.log_date, exc)
            return None
        return BronzeOutcome(
            object_key=outcome.object_key,
            sha256=outcome.sha256,
            size_bytes=outcome.size_bytes,
            deduplicated=outcome.deduplicated,
        )


def _num(value: float | int | None) -> float | None:
    return float(value) if value is not None else None
