"""One-command demo bootstrap: waits for infra, then seeds demo data.

Run inside the ingestion-api container (it has DB+MinIO grpc access):
    docker compose run --rm ingestion-api python scripts/seed_demo_data.py --days 90
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging

from sqlalchemy import text

from lifeops_core.config import get_settings
from lifeops_core.db.session import create_pg_engine
from lifeops_core.logging_setup import configure_logging

logger = logging.getLogger("seed_demo_data")


def _wait_for(engine, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.connect() as connection:
                connection.execute(text("select 1"))
            print("[seed] Postgres ready.")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"Postgres not reachable after {timeout}s: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data into LifeOps.")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)

    from scripts.generate_sample_data import generate

    engine = create_pg_engine(settings.database_url)
    print("[seed] Waiting for infrastructure...")
    _wait_for(engine, args.timeout)

    summary = generate(argparse.Namespace(days=args.days, seed=args.seed))
    print(json.dumps({"status": "ok", **summary}, indent=2))


if __name__ == "__main__":
    main()
