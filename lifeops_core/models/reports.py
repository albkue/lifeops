import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lifeops_core.db.base import Base


class ReportSnapshot(Base):
    """Immutable-ish payload snapshots of generated reports (weekly/monthly).

    Re-generation of the same period upserts the newer payload; the old one is
    superseded (we keep 'latest per period' rather than an event log).
    """

    __tablename__ = "report_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "report_type", "period_start", name="uq_report_snapshots_period"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
