from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lifeops_core.db.base import Base, TimestampedColumns


class PipelineConfig(Base, TimestampedColumns):
    """Runtime-tunable pipeline parameters (Life Balance weights, thresholds).

    Rows are read into typed dataclasses by the service layer; empty table
    falls back to sensible defaults built into settings.
    """

    __tablename__ = "pipeline_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
