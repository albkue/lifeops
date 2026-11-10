"""Bronze layer writer: raw payloads land in MinIO exactly once.

Design rules enforced here:
- The stored object layout is `{"payload": <source data>, "_lifeops_meta":
  {ingested_at, source, dataset, schema_version, extraction_window_*}}`.
  Our extractors work on parsed dicts (the JSON response we received), and the
  source data is preserved under the collision-free `payload` key - no
  re-shaping, no field dropping, no enrichment.
- Idempotency is enforced by the raw_source_objects ledger
  (unique on source+dataset+payload_sha256+extraction_window_start).
  A retried ingestion or replayed backfill of the same window is detected by
  SHA and skipped, so re-running a window never writes duplicate raw rows.
- Object keys are replay-friendly and hive-partitionable:
  bronze/{source}/{dataset}/extr_date=YYYY-MM-DD/ingested_at=...Z/{sha8}-{rand}.json
- No schema knowledge lives here. Schema evolution is tagged in the ledger via
  schema_version and consumed by Silver (Phase 4).
"""

import hashlib
import json
import logging
import uuid as uuid_module
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from lifeops_core.config import Settings
from lifeops_core.repositories.raw_source_objects import RawSourceObjectRepository
from lifeops_core.repositories.users import UserRepository
from lifeops_core.storage.object_store import MinioObjectStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BronzeWriteResult:
    object_key: str
    sha256: str
    size_bytes: int
    deduplicated: bool


def serialize_payload(
    payload: Mapping,
    envelope_meta: Mapping | None = None,
) -> bytes:
    """Serialize the stored Bronze object.

    Layout is intentionally `{"payload": <source data>, "_lifeops_meta": {...}}`
    so:
    - the source payload is preserved under a single, collision-free key, and
    - ingestion metadata (ingested_at / source / window / schema_version) rides
      in-band for replay without DB access.
    Silver parsers then make no assumptions about source payload shape.
    """
    wrapped = {"payload": payload, "_lifeops_meta": dict(envelope_meta or {})}
    return json.dumps(
        wrapped,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
        sort_keys=True,
    ).encode("utf-8")


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_bronze_key(
    source_name: str,
    dataset: str,
    window_start_date: date | None,
    ingested_at: datetime,
    payload_sha8: str,
) -> str:
    day = window_start_date if window_start_date else ingested_at.date()
    stamp = ingested_at.strftime("%Y%m%dT%H%M%S")
    suffix = uuid_module.uuid4().hex[:12]
    return (
        f"bronze/{source_name}/{dataset}/"
        f"extr_date={day}/ingested_at={stamp}Z/"
        f"{payload_sha8}-{suffix}.json"
    )


class BronzeStorage:
    """Facade over MinIO + the raw_source_objects ledger.

    A dedicated session factory is used so bronze writes are committed
    independently of caller transactions (e.g. after a manual-log commit).
    """

    def __init__(
        self,
        store: MinioObjectStore,
        session_factory: sessionmaker[Session],
        default_schema_version: str = "v1",
    ) -> None:
        self.store = store
        self.session_factory = session_factory
        self.schema_version = default_schema_version

    def write(
        self,
        *,
        source_name: str,
        dataset: str,
        payload: Mapping,
        ingestion_run_id: uuid_module.UUID | None = None,
        user_id: uuid_module.UUID | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        ingested_at: datetime | None = None,
        schema_version: str | None = None,
        attributes: dict | None = None,
    ) -> BronzeWriteResult:
        # Digest over the SOURCE payload only (not the envelope), so re-running
        # the same extraction - or re-sending the same event hours later - is
        # detected as a duplicate. The envelope (ingested_at etc.) changes
        # between calls and must never influence identity.
        raw_identity = serialize_payload(payload)
        digest = sha256_hex(raw_identity)
        digest8 = digest[:8]
        now = ingested_at or datetime.now(UTC)
        envelope_meta = {
            "ingested_at": now.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
            "source": source_name,
            "dataset": dataset,
            "schema_version": schema_version or self.schema_version,
            "extraction_window_start": (
                window_start.strftime("%Y-%m-%dT%H:%M:%S.%f%z") if window_start else None
            ),
            "extraction_window_end": (
                window_end.strftime("%Y-%m-%dT%H:%M:%S.%f%z") if window_end else None
            ),
        }
        raw = serialize_payload(payload, envelope_meta)

        with self.session_factory() as session:
            repo = RawSourceObjectRepository(session)
            day = window_start.date() if window_start else now.date()
            key = build_bronze_key(source_name, dataset, day, now, digest8)
            # 1. Ledger check (fast path)
            if repo.identity_exists(source_name, dataset, digest, window_start):
                return BronzeWriteResult(
                    object_key="<existing>", sha256=digest, size_bytes=len(raw), deduplicated=True
                )

            # 2. Put object, then ledger row (idempotency ledger is the truth).
            self.store.put_bytes(key, raw)
            try:
                repo.insert(
                    source_name=source_name,
                    dataset=dataset,
                    object_key=key,
                    payload_sha256=digest,
                    payload_bytes=len(raw),
                    ingested_at=now,
                    extraction_window_start=window_start,
                    extraction_window_end=window_end,
                    schema_version=schema_version or self.schema_version,
                    ingestion_run_id=ingestion_run_id,
                    user_id=user_id,
                    attributes=attributes or {},
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                logger.warning(
                    "Bronze identity race on %s/%s sha=%s; treating as duplicate.",
                    source_name,
                    dataset,
                    digest8,
                )
                return BronzeWriteResult(
                    object_key=key, sha256=digest, size_bytes=len(raw), deduplicated=True
                )

        return BronzeWriteResult(
            object_key=key, sha256=digest, size_bytes=len(raw), deduplicated=False
        )

    def write_batch(
        self,
        *,
        source_name: str,
        dataset: str,
        payloads: list[Mapping],
        ingestion_run_id: uuid_module.UUID | None = None,
        user_id: uuid_module.UUID | None = None,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        ingested_at: datetime | None = None,
        schema_version: str | None = None,
        attributes: dict | None = None,
    ) -> list[BronzeWriteResult]:
        """Convenience for window-level batches (one payload per object).

        Each payload gets its own object + ledger row; duplicates inside the
        batch are collapsed by SHA automatically.
        """
        return [
            self.write(
                source_name=source_name,
                dataset=dataset,
                payload=payload,
                ingestion_run_id=ingestion_run_id,
                user_id=user_id,
                window_start=window_start,
                window_end=window_end,
                ingested_at=ingested_at,
                schema_version=schema_version,
                attributes=attributes,
            )
            for payload in payloads
        ]


def ensure_default_user(
    session_factory: sessionmaker[Session], settings: Settings
) -> uuid_module.UUID:
    """Standalone helper (used by scripts), mirrors the API bootstrap."""
    with session_factory() as session:
        return UserRepository(session).ensure_default_user(settings).id
