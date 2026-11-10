import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lifeops_core.db.base import Base, TimestampedColumns, UUIDPrimaryKey


class Expense(Base, UUIDPrimaryKey, TimestampedColumns):
    """Personal expense transactions (Populated from manual API or CSV in Phase 11)."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("length(currency) = 3", name="currency_iso3"),
        Index("ix_expenses_user_date", "user_id", "expense_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", foreign_keys=[user_id], viewonly=True)
