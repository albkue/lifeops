"""Bronze integrity audit (Phase 2).

Walk the raw_source_objects ledger and verify each object:
1. exists in the object store,
2. parses as the Bronze envelope (`{"payload": ..., "_lifeops_meta": ...}`),
3. re-canonicalizes to the exact ledger digest (source-payload identity),
4. byte length matches the ledger row.

Read-only by design: Phase 2 *detects*. Repairing means replaying from a
source extractor (Phase 6+) — Bronze alone cannot regenerate a lost payload,
because there is no second copy of the data.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import datetime as _datetime

from sqlalchemy.orm import Session, sessionmaker

from lifeops_core.repositories.raw_source_objects import RawSourceObjectRepository
from lifeops_core.storage.bronze import serialize_payload, sha256_hex
from lifeops_core.storage.object_store import MinioObjectStore

logger = logging.getLogger(__name__)


class PayloadVerificationError(Exception):
    """Raised when stored Bronze bytes do not hash to the ledger digest."""

    def __init__(self, message: str, actual_sha256: str | None = None) -> None:
        super().__init__(message)
        self.actual_sha256 = actual_sha256


def verify_bronze_object(raw_bytes: bytes, expected_sha256: str) -> None:
    """Verify stored Bronze bytes against the ledger digest.

    Identity rule (must match BronzeStorage.write): the ledger digest is
    sha256 over the canonical serialization of `{"payload": <source data>,
    "_lifeops_meta": {}}` — i.e. the SOURCE payload only. The written envelope
    (`_lifeops_meta` with ingested_at etc.) intentionally does NOT participate.
    Verification therefore re-extracts the `payload` mapping from the stored
    JSON and re-canonicalizes it exactly the same way.
    """
    try:
        doc = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise PayloadVerificationError(f"object is not valid JSON: {exc}") from None
    payload = doc.get("payload") if isinstance(doc, dict) else None
    if payload is None:
        raise PayloadVerificationError("object has no `payload` key")
    actual = sha256_hex(serialize_payload(payload))
    if actual != expected_sha256:
        raise PayloadVerificationError(
            f"payload digest mismatch: expected {expected_sha256[:12]}, got {actual[:12]}",
            actual_sha256=actual,
        )


@dataclass(frozen=True)
class BronzeAuditFinding:
    object_key: str
    payload_sha256: str
    problem: str  # missing | corrupt | unreadable | size_mismatch
    detail: str | None = None


@dataclass(frozen=True)
class BronzeAuditSummary:
    source_name: str
    dataset: str | None
    checked_at: str
    ledger_rows: int
    ok: int
    missing: int
    corrupt: int
    problems: list[BronzeAuditFinding]
    truncated: bool


@dataclass(frozen=True)
class BronzeAuditOptions:
    max_problems: int = 200


class BronzeAuditor:
    """Ledger-driven Bronze verifier bound to one object store + session factory."""

    def __init__(
        self,
        store: MinioObjectStore,
        session_factory: sessionmaker[Session],
        options: BronzeAuditOptions | None = None,
    ) -> None:
        self.store = store
        self.session_factory = session_factory
        self.options = options or BronzeAuditOptions()

    def audit(
        self,
        source_name: str,
        *,
        dataset: str | None = None,
        window_start: _datetime | None = None,
        window_end: _datetime | None = None,
    ) -> BronzeAuditSummary:
        problems: list[BronzeAuditFinding] = []
        ok_count = 0
        missing_count = 0
        corrupt_count = 0
        truncated = False
        seen_rows = 0

        with self.session_factory() as session:
            repo = RawSourceObjectRepository(session)
            for row in repo.iter_for_source(
                source_name=source_name,
                dataset=dataset,
                window_start=window_start,
                window_end=window_end,
            ):
                seen_rows += 1
                problem: str | None = None
                detail: str | None = None

                if not self.store.object_exists(row.object_key):
                    problem, missing_count = "missing", missing_count + 1
                else:
                    try:
                        raw = self.store.get_object_bytes(row.object_key)
                        verify_bronze_object(raw, row.payload_sha256)
                        if len(raw) != row.payload_bytes:
                            problem = "size_mismatch"
                            detail = f"store size {len(raw)} != ledger {row.payload_bytes}"
                        else:
                            ok_count += 1
                    except PayloadVerificationError as exc:
                        problem, corrupt_count = "corrupt", corrupt_count + 1
                        detail = str(exc)
                    except Exception as exc:  # transport/protocol-level failure
                        problem = "unreadable"
                        detail = str(exc)

                if problem is not None:
                    problems.append(
                        BronzeAuditFinding(
                            object_key=row.object_key,
                            payload_sha256=row.payload_sha256,
                            problem=problem,
                            detail=detail,
                        )
                    )
                    if len(problems) >= self.options.max_problems:
                        truncated = True
                        break

        checked_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        return BronzeAuditSummary(
            source_name=source_name,
            dataset=dataset,
            checked_at=checked_at,
            ledger_rows=seen_rows,
            ok=ok_count,
            missing=missing_count,
            corrupt=corrupt_count,
            problems=problems,
            truncated=truncated,
        )
