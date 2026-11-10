"""Pydantic schema validation + normalization rules."""

import pytest
from pydantic import ValidationError

from lifeops_core.schemas import DailyLogCreate, DailyLogUpdate

pytestmark = pytest.mark.unit


def valid(**overrides):
    base = {
        "log_date": "2026-11-09",
        "sleep_hours": 7.5,
        "mood_score": 4,
        "study_hours": 2,
        "coding_hours": 5,
        "workout_minutes": 30,
        "soccer_minutes": 0,
        "notes": "ok day",
        "tags": ["Deep-Work "],
    }
    base.update(overrides)
    return base


class TestDailyLogCreate:
    def test_accepts_full_record(self):
        record = DailyLogCreate(**valid())
        assert record.log_date.isoformat() == "2026-11-09"
        assert record.sleep_hours == 7.5

    def test_mood_bounds_enforced(self):
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(mood_score=6))
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(mood_score=0))

    def test_hours_bounds_enforced(self):
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(sleep_hours=25))
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(coding_hours=-1))

    def test_minutes_bounds_enforced(self):
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(workout_minutes=1441))
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(soccer_minutes=-5))

    def test_tags_normalized_trimmed_lowercased_deduped(self):
        record = DailyLogCreate(**valid(tags=[" Deep-Work ", "deep-work", "FOCUS", ""]))
        assert record.tags == ["deep-work", "focus"]

    def test_oversized_tag_rejected(self):
        with pytest.raises(ValidationError):
            DailyLogCreate(**valid(tags=["x" * 40]))

    def test_empty_notes_become_none(self):
        record = DailyLogCreate(**valid(notes="   "))
        assert record.notes is None


class TestDailyLogUpdate:
    def test_exclude_unset_semantics(self):
        update = DailyLogUpdate(mood_score=5)
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"mood_score": 5}

    def test_full_update(self):
        update = DailyLogUpdate(**{k: v for k, v in valid().items() if k != "log_date"})
        assert update.workout_minutes == 30
