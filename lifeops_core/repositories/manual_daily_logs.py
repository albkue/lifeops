import uuid
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lifeops_core.models import ManualDailyLog
from lifeops_core.schemas import DailyLogCreate, DailyLogUpdate


class ManualDailyLogRepository:
    """CRUD for manual_daily_logs. Never commits - callers commit."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: uuid.UUID, log_id: uuid.UUID) -> ManualDailyLog | None:
        stmt = select(ManualDailyLog).where(
            ManualDailyLog.user_id == user_id,
            ManualDailyLog.id == log_id,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_by_date(self, user_id: uuid.UUID, log_date: date) -> ManualDailyLog | None:
        stmt = select(ManualDailyLog).where(
            ManualDailyLog.user_id == user_id,
            ManualDailyLog.log_date == log_date,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_range(
        self,
        user_id: uuid.UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[ManualDailyLog], int]:
        base = select(ManualDailyLog).where(ManualDailyLog.user_id == user_id)
        if start_date:
            base = base.where(ManualDailyLog.log_date >= start_date)
        if end_date:
            base = base.where(ManualDailyLog.log_date <= end_date)

        total = self.session.execute(select(func.count()).select_from(base.subquery())).scalar_one()

        rows = (
            self.session.execute(
                base.order_by(ManualDailyLog.log_date.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    def add(self, user_id: uuid.UUID, data: DailyLogCreate) -> ManualDailyLog:
        row = ManualDailyLog(
            user_id=user_id,
            log_date=data.log_date,
            sleep_hours=data.sleep_hours,
            mood_score=data.mood_score,
            study_hours=data.study_hours,
            coding_hours=data.coding_hours,
            workout_minutes=data.workout_minutes,
            soccer_minutes=data.soccer_minutes,
            notes=data.notes,
            tags=list(data.tags or []),
        )
        self.session.add(row)
        return row

    def upsert(self, user_id: uuid.UUID, data: DailyLogCreate) -> tuple[ManualDailyLog, bool]:
        """Create the day's log, or fill in missing fields on an existing row.

        Upsert semantics (mobile-friendly: same URL always 'works').
        Update semantics favor explicit PATCH when we need to OVERRIDE a
        previously logged value back to 'not tracked'.

        Returns (row, created).
        """
        row = self.get_by_date(user_id, data.log_date)
        if row is None:
            row = self.add(user_id, data)
            return row, True
        self.apply_update(row, DailyLogUpdate(**data.model_dump(exclude={"log_date"})))
        return row, False

    def apply_update(self, row: ManualDailyLog, data: DailyLogUpdate) -> ManualDailyLog:
        """Patch only explicitly provided fields; untrackable fields ignored."""
        updates = data.model_dump(exclude_unset=True, exclude_none=True)
        for field_name, value in updates.items():
            if field_name == "tags":
                value = list(value or [])
            setattr(row, field_name, value)
        return row

    def delete(self, row: ManualDailyLog) -> None:
        self.session.delete(row)

    def count(self, user_id: uuid.UUID | None = None) -> int:
        stmt = select(func.count()).select_from(ManualDailyLog)
        if user_id:
            stmt = stmt.where(ManualDailyLog.user_id == user_id)
        return int(self.session.execute(stmt).scalar_one())

    def purge_user(self, user_id: uuid.UUID) -> int:
        result = self.session.execute(
            delete(ManualDailyLog).where(ManualDailyLog.user_id == user_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)
