"""Standalone Bronze integrity audit (works with or without the API running).

Run inside a service container (has DB + object store network access):
    docker compose run --rm ingestion-api python scripts/audit_bronze.py \
        --source github --window-start 2026-11-01T00:00:00Z --window-end 2026-11-08T23:59:59Z

Exit codes: 0 = clean; 1 = problems found; 2 = audit failed to run.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifeops_core.config import get_settings
from lifeops_core.db.session import create_pg_engine, make_session_factory
from lifeops_core.logging_setup import configure_logging
from lifeops_core.storage.audit import BronzeAuditor
from lifeops_core.storage.object_store import MinioObjectStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Bronze integrity (ledger vs object store).")
    parser.add_argument("--source", required=True, help="e.g. github, calendar, weather")
    parser.add_argument("--dataset", default=None, help="optional dataset filter")
    parser.add_argument(
        "--window-start",
        default=None,
        help="ISO datetimes; audit the overlap window (UTC, e.g. 2026-11-01T00:00:00Z)",
    )
    parser.add_argument("--window-end", default=None)
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)

    def _parse(value: str | None):
        if value is None:
            return None
        value = value.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)

    engine = create_pg_engine(settings.database_url)
    store = MinioObjectStore.from_settings(settings)
    auditor = BronzeAuditor(store, make_session_factory(engine))

    report = auditor.audit(
        args.source,
        dataset=args.dataset or None,
        window_start=_parse(args.window_start),
        window_end=_parse(args.window_end),
    )
    engine.dispose()

    line = (
        f"source={report.source_name} ledger={report.ledger_rows} ok={report.ok} "
        f"missing={report.missing} corrupt={report.corrupt} truncated={report.truncated}"
    )
    print(line)
    if report.problems:
        for problem in report.problems:
            print(
                json.dumps(
                    {
                        "problem": problem.problem,
                        "object_key": problem.object_key,
                        "detail": problem.detail,
                    }
                )
            )
    return 0 if not report.problems else 1


if __name__ == "__main__":
    sys.exit(main())
