"""Pure unit tests: no external services required."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.unit

from lifeops_core.timeutils import ReportingClock, utc_day_bounds  # noqa: E402


class TestReportingClock:
    def test_today_returns_date(self):
        clock = ReportingClock("Asia/Ho_Chi_Minh")
        assert isinstance(clock.today(), date)

    def test_local_day_bounds_utc_offset_plus7(self):
        clock = ReportingClock("Asia/Ho_Chi_Minh")
        start, end = clock.local_day_bounds_utc(date(2026, 11, 10))
        assert start == datetime(2026, 11, 9, 17, 0, tzinfo=UTC)
        assert end == datetime(2026, 11, 10, 17, 0, tzinfo=UTC)

    def test_bounds_are_24_hours_half_open(self):
        clock = ReportingClock("Asia/Ho_Chi_Minh")
        start, end = clock.local_day_bounds_utc(date(2026, 11, 10))
        assert (end - start).total_seconds() == 24 * 3600

    def test_unknown_timezone_raises_clear_error(self):
        with pytest.raises(ValueError):
            ReportingClock("Asia/Definitely_Not_A_Zone")


class TestUtcDayBounds:
    def test_day_bounds(self):
        start, end = utc_day_bounds(date(2026, 11, 10))
        assert start == datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
        assert (end - start).total_seconds() == 24 * 3600

    def test_zoneinfo_module_present(self):
        assert ZoneInfo("Asia/Ho_Chi_Minh").key == "Asia/Ho_Chi_Minh"
