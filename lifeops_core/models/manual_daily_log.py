import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lifeops_core.db.base import Base, TimestampedColumns, UUIDPrimaryKey


class ManualDailyLog(Base, UUIDPrimaryKey, TimestampedColumns):
    """One row per local calendar day with self-reported habit data.

    All fields are NULLable on purpose: people log incompletely; the Life
    Balance Score treats NULL as 'not tracked that day', not as 0.
    """

    __tablename__ = "manual_daily_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "log_date", name="uq_manual_daily_logs_user_date"),
        CheckConstraint("mood_score IS NULL OR mood_score BETWEEN 1 AND 5", name="mood_range"),
        CheckConstraint("sleep_hours IS NULL OR sleep_hours BETWEEN 0 AND 24", name="sleep_range"),
        CheckConstraint("study_hours IS NULL OR study_hours BETWEEN 0 AND 24", name="study_range"),
        CheckConstraint(
            "coding_hours IS NULL OR coding_hours BETWEEN 0 AND 24", name="coding_range"
        ),
        CheckConstraint(
            "workout_minutes IS NULL OR workout_minutes BETWEEN 0 AND 1440",
            name="workout_range",
        ),
        CheckConstraint(
            "soccer_minutes IS NULL OR soccer_minutes BETWEEN 0 AND 1440",
            name="soccer_range",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)

    sleep_hours: Mapped[float | None] = mapped_column(Numeric(4, 2))
    mood_score: Mapped[int | None] = mapped_column()
    study_hours: Mapped[float | None] = mapped_column(Numeric(4, 2))
    coding_hours: Mapped[float | None] = mapped_column(Numeric(4, 2))
    workout_minutes: Mapped[int | None] = mapped_column()
    soccer_minutes: Mapped[int | None] = mapped_column()

    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, server_default="{}")

    user = relationship("User", foreign_keys=[user_id], viewonly=True)
