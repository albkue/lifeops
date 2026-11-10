import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lifeops_core.db.base import Base, TimestampedColumns, UUIDPrimaryKey


class IngestionRun(Base, UUIDPrimaryKey, TimestampedColumns):
    """One extraction run of one source (manual / scheduled / backfill)."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','success','failed','partial')", name="status"
        ),
        CheckConstraint("run_type IN ('manual','scheduled','backfill')", name="run_type"),
        CheckConstraint("records_extracted >= 0", name="records_extracted_nonneg"),
        CheckConstraint("records_loaded >= 0", name="records_loaded_nonneg"),
        CheckConstraint("error_count >= 0", name="error_count_nonneg"),
        CheckConstraint("window_end >= window_start", name="window_valid"),
        Index("ix_ingestion_runs_source_started", "source_name", text("started_at DESC")),
        Index("ix_ingestion_runs_status_started", "status", text("started_at DESC")),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    run_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_extracted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_loaded: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    trigger: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    run_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class IngestionError(Base, UUIDPrimaryKey):
    """Structured error row attached to a run (kept out of the payload)."""

    __tablename__ = "ingestion_errors"

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # extract | validate | load
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RawSourceObject(Base, UUIDPrimaryKey):
    """Catalog row for every object written to Bronze in MinIO.

    The DB row is the idempotency ledger: (source, dataset, payload sha256,
    extraction window) defines exact-once writes even with retries.
    """

    __tablename__ = "raw_source_objects"
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "dataset",
            "payload_sha256",
            "extraction_window_start",
            name="uq_raw_source_objects_identity",
        ),
        Index("ix_raw_source_objects_ingested_at", text("ingested_at DESC")),
        Index("ix_raw_source_objects_source_day", "source_name", "extraction_window_start"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g. commits / pull_requests / events / recently_played / daily_logs
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(16), default="v1", server_default="v1")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Small non-source attributes (record counts inside payload, page token...).
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")

    run = relationship("IngestionRun", foreign_keys=[ingestion_run_id], viewonly=True)
