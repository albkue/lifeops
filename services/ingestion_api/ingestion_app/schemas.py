"""Typed response/request models exposed over HTTP (OpenAPI visible)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lifeops_core.schemas import BronzeRef, DailyLogRead

ServiceName = Literal["ingestion-api", "insights-api"]


# -------------------------------- health -----------------------------------
class ComponentHealth(BaseModel):
    name: str
    status: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unavailable"]
    service: ServiceName
    components: list[ComponentHealth]
    version: str


class MetricCount(BaseModel):
    key: str
    value: int


class LatestRunInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_name: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None = None


class MetricsResponse(BaseModel):
    service: ServiceName
    generated_at: datetime
    counts: list[MetricCount]
    latest_runs: list[LatestRunInfo]


# ------------------------------ daily logs ---------------------------------
class DailyLogUpsertResult(BaseModel):
    record: DailyLogRead
    created: bool
    bronze: BronzeRef | None = Field(
        description="Bronze raw-object reference; None when MinIO was unreachable."
    )


class DailyLogPage(BaseModel):
    items: list[DailyLogRead]
    total: int
    limit: int
    offset: int


class DailyLogRangeQuery(BaseModel):
    start_date: date | None = Field(None, description="Inclusive lower bound")
    end_date: date | None = Field(None, description="Inclusive upper bound")
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0, le=100_000)


# ------------------------------ ingestion -----------------------------------
class IngestionWindowRequest(BaseModel):
    """Optional window for /run, REQUIRED for /backfill."""

    window_start: datetime | None = Field(
        None, description="UTC extraction start (inclusive), ISO-8601"
    )
    window_end: datetime | None = Field(
        None, description="UTC extraction end (exclusive), ISO-8601"
    )

    @model_validator(mode="after")
    def window_order(self) -> "IngestionWindowRequest":
        if self.window_start is not None and self.window_end is not None:
            if self.window_start > self.window_end:
                raise ValueError("window_start must be <= window_end")
            if (self.window_end - self.window_start) > timedelta(days=120):
                raise ValueError("window longer than 120 days is not allowed")
        return self


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_name: str
    run_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    records_extracted: int
    records_loaded: int
    error_count: int
    error_message: str | None


class IngestionRunPage(BaseModel):
    items: list[IngestionRunRead]
    total: int
    limit: int
    offset: int


__all__ = [
    "ComponentHealth",
    "DailyLogPage",
    "DailyLogRangeQuery",
    "DailyLogRead",
    "DailyLogUpsertResult",
    "HealthResponse",
    "IngestionRunPage",
    "IngestionRunRead",
    "IngestionWindowRequest",
    "LatestRunInfo",
    "MetricCount",
    "MetricsResponse",
]
