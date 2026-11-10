import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lifeops_core.db.base import Base, TimestampedColumns, UUIDPrimaryKey
from lifeops_core.models.enums import ConnectionMode, ConnectionStatus


class SourceConnection(Base, UUIDPrimaryKey, TimestampedColumns):
    """Per-user connection to an external source (OAuth creds / config).

    Credentials are stored as JSONB for now — Phase 6 documents the design
    (env-only secrets in v1; encrypted-at-rest is an explicit decision point).
    """

    __tablename__ = "source_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "source_name", name="uq_source_connections_user_source"),
        CheckConstraint(
            "status IN ('ok','error','expiring','disabled')",
            name="status",
        ),
        CheckConstraint("mode IN ('live','demo')", name="mode"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(16), default=ConnectionMode.LIVE.value, server_default="live", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=ConnectionStatus.OK.value, server_default="ok", nullable=False
    )
    # Encrypted/encoded credentials vary per source: keep opaque.
    credentials: Mapped[dict | None] = mapped_column(JSONB)
    # Non-secret config (calendar ids, budget defaults, location, ...).
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    # Incremental sync cursor (latest updated_at / page token per source).
    cursor: Mapped[dict | None] = mapped_column(JSONB)
    last_sync_at: Mapped[datetime | None] = mapped_column()

    user = relationship("User", foreign_keys=[user_id], viewonly=True)
