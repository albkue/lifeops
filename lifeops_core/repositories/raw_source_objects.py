import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifeops_core.models import RawSourceObject


class RawSourceObjectRepository:
    """Ledger rows for every Bronze object written to MinIO (idempotency)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def identity_exists(
        self,
        source_name: str,
        dataset: str,
        payload_sha256: str,
        extraction_window_start: datetime | None,
    ) -> bool:
        stmt = (
            select(func.count())
            .select_from(RawSourceObject)
            .where(
                RawSourceObject.source_name == source_name,
                RawSourceObject.dataset == dataset,
                RawSourceObject.payload_sha256 == payload_sha256,
                RawSourceObject.extraction_window_start == extraction_window_start,
            )
        )
        return self.session.execute(stmt).scalar_one() > 0

    def insert(
        self,
        *,
        source_name: str,
        dataset: str,
        object_key: str,
        payload_sha256: str,
        payload_bytes: int,
        ingested_at: datetime,
        extraction_window_start: datetime | None = None,
        extraction_window_end: datetime | None = None,
        schema_version: str = "v1",
        ingestion_run_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        attributes: dict | None = None,
    ) -> RawSourceObject:
        row = RawSourceObject(
            source_name=source_name,
            dataset=dataset,
            object_key=object_key,
            payload_sha256=payload_sha256,
            payload_bytes=payload_bytes,
            ingested_at=ingested_at,
            extraction_window_start=extraction_window_start,
            extraction_window_end=extraction_window_end,
            schema_version=schema_version,
            ingestion_run_id=ingestion_run_id,
            user_id=user_id,
            attributes=attributes or {},
        )
        self.session.add(row)
        self.session.flush()
        return row
