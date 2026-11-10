import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lifeops_core.db.base import Base, TimestampedColumns, UUIDPrimaryKey


class Alert(Base, UUIDPrimaryKey, TimestampedColumns):
    """One detected alert (anomaly rule fired). Lifecycle: open → acknowledged/resolved."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("severity IN ('info','warning','critical')", name="severity"),
        CheckConstraint("status IN ('open','acknowledged','resolved')", name="status"),
        UniqueConstraint("user_id", "rule_name", "detected_at", name="uq_alerts_rule_detection"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    rule_name: Mapped[str] = mapped_column(String(96), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationChannel(Base, UUIDPrimaryKey, TimestampedColumns):
    """Pluggable alert channel config (console always exists implicitly)."""

    __tablename__ = "notification_channels"
    __table_args__ = (
        CheckConstraint("type IN ('console','telegram','discord','email')", name="type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # console | telegram | discord | email
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Channel secrets must NOT be stored here in plaintext (Telegram token,
    # Discord webhook URL). Secrets stay in env; config references env names.
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
