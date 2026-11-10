"""Ledger repository for raw Bronze objects (idempotency + Phase-2 audit/catalog)."""

import uuid
from collections.abc import Iterator
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

    # ------------------------------------------------------------------ read
    def iter_for_source(
        self,
        *,
        source_name: str,
        dataset: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        batch_size: int = 500,
    ) -> Iterator[RawSourceObject]:
        """Stream ledger rows for a source (optionally filtered).

        Filtering semantics: rows whose extraction window OVERLAPS
        [window_start, window_end). Rows without a window NEVER match an
        explicit window query (consistent with ingestion_runs).
        """
        stmt = (
            select(RawSourceObject)
            .where(RawSourceObject.source_name == source_name)
            .order_by(RawSourceObject.extraction_window_start.asc().nullslast())
        )
        if dataset is not None:
            stmt = stmt.where(RawSourceObject.dataset == dataset)
        if window_start is not None:
            stmt = stmt.where(RawSourceObject.extraction_window_end > window_start)
        if window_end is not None:
            stmt = stmt.where(RawSourceObject.extraction_window_start < window_end)
        stmt = stmt.execution_options(yield_per=batch_size)
        yield from self.session.execute(stmt).scalars().yield_per(batch_size)

    def list_page(
        self,
        *,
        source_name: str | None = None,
        dataset: str | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RawSourceObject], int]:
        """Paginated catalog view used by GET /api/v1/ingestion/objects."""
        base = select(RawSourceObject)
        counts = select(func.count()).select_from(RawSourceObject)
        if source_name is not None:
            base = base.where(RawSourceObject.source_name == source_name)
            counts = counts.where(RawSourceObject.source_name == source_name)
        if dataset is not None:
            base = base.where(RawSourceObject.dataset == dataset)
            counts = counts.where(RawSourceObject.dataset == dataset)
        if window_start is not None:
            overlapping = RawSourceObject.extraction_window_end > window_start
            base = base.where(overlapping)
            counts = counts.where(overlapping)
        if window_end is not None:
            overlapping = RawSourceObject.extraction_window_start < window_end
            base = base.where(overlapping)
            counts = counts.where(overlapping)

        total = self.session.execute(counts).scalar_one()
        rows = (
            self.session.execute(
                base.order_by(RawSourceObject.ingested_at.desc()).offset(offset).limit(limit)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    def count_by_source(self, source_name: str) -> int:
        stmt = (
            select(func.count())
            .select_from(RawSourceObject)
            .where(RawSourceObject.source_name == source_name)
        )
        return int(self.session.execute(stmt).scalar_one())
