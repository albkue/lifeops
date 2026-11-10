"""Time helpers.

Invariants:
- All datetimes stored in the warehouse are timezone-aware UTC.
- Day boundaries ("today", week start, report windows) are computed in the
  configured reporting timezone (UTC+7 for this deployment) then converted
  to UTC intervals.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from lifeops_core.config import Settings


class ReportingClock:
    """Day-boundary arithmetic bound to the reporting timezone."""

    def __init__(self, timezone_name: str) -> None:
        try:
            self.tz = ZoneInfo(timezone_name)
        except Exception as exc:
            raise ValueError(f"Unknown LIFEOPS_TIMEZONE '{timezone_name}': {exc}") from exc

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReportingClock":
        return cls(settings.timezone_name)

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        """'Today' as seen by the user, not by the server."""
        return self.now_utc().astimezone(self.tz).date()

    def local_day_bounds_utc(self, day: date) -> tuple[datetime, datetime]:
        """Half-open [start, end) UTC window covering the local calendar day."""
        local_start = datetime.combine(day, time.min, tzinfo=self.tz)
        local_end = local_start + timedelta(days=1)
        return (
            local_start.astimezone(UTC),
            local_end.astimezone(UTC),
        )


def utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    """Half-open [start, end) window for a plain UTC date (Bronze windows)."""
    d = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return d, d + timedelta(days=1)
