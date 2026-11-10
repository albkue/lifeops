"""Shared SQLAlchemy/Pydantic schemas used across services and scripts."""

import uuid
from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


# ----------------------------- pagination ----------------------------------
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ------------------------------ daily log ----------------------------------
class DailyLogBase(BaseModel):
    sleep_hours: float | None = Field(None, ge=0, le=24, description="Hours slept")
    mood_score: int | None = Field(None, ge=1, le=5, description="Self rating 1-5")
    study_hours: float | None = Field(None, ge=0, le=24, description="Focused study hours")
    coding_hours: float | None = Field(None, ge=0, le=24, description="Focused coding hours")
    workout_minutes: int | None = Field(None, ge=0, le=1440)
    soccer_minutes: int | None = Field(None, ge=0, le=1440)
    notes: str | None = Field(None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        cleaned = []
        for raw in value:
            tag = raw.strip().lower()
            if not tag:
                continue
            if len(tag) > 32:
                raise ValueError("tag max length is 32 characters")
            if tag not in cleaned:
                cleaned.append(tag)
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class DailyLogCreate(DailyLogBase):
    log_date: date = Field(..., description="Local calendar day this log belongs to")

    # NOTE: future-date validation is intentionally NOT a static schema rule:
    # "today" depends on the reporting timezone (UTC+7 + DST-free), so the
    # service layer (with its ReportingClock) performs that check and raises
    # DomainValidationError.


class DailyLogUpdate(DailyLogBase):
    pass


class DailyLogRead(DailyLogBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    log_date: date
    sleep_hours: float | None
    mood_score: int | None
    study_hours: float | None
    coding_hours: float | None
    workout_minutes: int | None
    soccer_minutes: int | None
    notes: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ------------------------------ bronze refs --------------------------------
class BronzeRef(BaseModel):
    object_key: str
    sha256: str
    size_bytes: int
    deduplicated: bool


__all__ = [
    "BronzeRef",
    "DailyLogBase",
    "DailyLogCreate",
    "DailyLogRead",
    "DailyLogUpdate",
    "Page",
]
