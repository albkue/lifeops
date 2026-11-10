"""Source adapter registry.

Adapters implement the SourceAdapter protocol and self-register here when
their phase lands:
- Phase 6: github
- Phase 7: calendar
- Phase 11: spotify, weather, expenses

In Phase 1 the registry is intentionally empty: /ingestion/{source}/run
returns a structured HTTP 501 for known-but-unimplemented sources, which
documents the feature graph honestly rather than faking runs.
"""

from collections.abc import Mapping
from typing import Protocol

from sqlalchemy.orm import Session

from lifeops_core.models import IngestionRun
from lifeops_core.storage.bronze import BronzeStorage

ADAPTERS: dict[str, "SourceAdapter"] = {}


class SourceAdapter(Protocol):
    """Contract for source extractors (implemented incrementally)."""

    source_name: str

    def run(self, *, run: IngestionRun, session: Session, storage: BronzeStorage | None) -> None:
        """Extract a window, verify (schema+contract checks), write Bronze.

        Implementations are responsible for:
        - incremental cursor handling (source_connections.cursor)
        - rate limits, retries, backoff
        - updating IngestionRun counters before returning
        """
        ...


def register(adapter: SourceAdapter) -> None:
    ADAPTERS[adapter.source_name] = adapter


def get_adapter(source_name: str) -> SourceAdapter | None:
    return ADAPTERS.get(source_name)


def available_sources() -> Mapping[str, SourceAdapter]:
    return dict(ADAPTERS)
