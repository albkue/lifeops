"""Bronze catalog + integrity audit service (Phase 2).

Audit is intentionally a *detection* service: it reports missing/corrupt
objects. Repair requires the producing extractor (Phase 6+) — the extractor is
the only holder of a second copy of the data.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from lifeops_core.domain_errors import DomainValidationError
from lifeops_core.models import RawSourceObject
from lifeops_core.repositories.raw_source_objects import RawSourceObjectRepository
from lifeops_core.storage.audit import BronzeAuditor, BronzeAuditSummary
from lifeops_core.storage.object_store import MinioObjectStore

logger = logging.getLogger(__name__)


class BronzeIntrospectionService:
    """Read-only operations over the raw_source_objects ledger + object store."""

    def __init__(
        self,
        session: Session,
        session_factory: sessionmaker[Session],
        store: MinioObjectStore | None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.store = store

    # --------------------------------------------------------------- catalog
    def list_objects(
        self,
        *,
        source_name: str | None = None,
        dataset: str | None = None,
        window_from: datetime | None = None,
        window_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RawSourceObject], int]:
        """Paginated ledger catalog, newest ingested first."""
        if limit < 1 or limit > 200:
            raise DomainValidationError("limit must be 1..200")
        if offset < 0:
            raise DomainValidationError("offset must be >= 0")
        repo = RawSourceObjectRepository(self.session)
        return repo.list_page(
            source_name=source_name,
            dataset=dataset,
            window_start=window_from,
            window_end=window_to,
            limit=limit,
            offset=offset,
        )

    # ---------------------------------------------------------------- audit
    def audit_source(
        self,
        *,
        source_name: str,
        dataset: str | None = None,
        window_from: datetime | None = None,
        window_to: datetime | None = None,
        max_problems: int = 200,
    ) -> BronzeAuditSummary:
        if self.store is None:
            raise DomainValidationError("object store is unavailable; cannot run a Bronze audit")
        auditor = BronzeAuditor(self.store, self.session_factory)
        return auditor.audit(
            source_name,
            dataset=dataset,
            window_start=window_from,
            window_end=window_to,
        )
