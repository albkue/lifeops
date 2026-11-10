"""Generate deterministic sample data for local demo/testing.

Generator-only data both:
1. upserts warehouse rows (manual_daily_logs, expenses, ingestion_runs), and
2. stores raw-shaped payloads into Bronze via BronzeStorage, exactly as an
   extractor would — so the medallion path is exercised end to end without
   real API credentials, and the Silver/dbt phases have real Bronze input.

Usage (inside the ingestion-api container, which has DB+MinIO network access):
    docker compose run --rm ingestion-api python scripts/generate_sample_data.py \
        --days 90 --seed 42

The generator NEVER talks to external APIs.
"""

import argparse
import json
import logging
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lifeops_core.config import Settings, get_settings
from lifeops_core.db.session import create_pg_engine, make_session_factory
from lifeops_core.logging_setup import configure_logging
from lifeops_core.models import Expense
from lifeops_core.models.enums import IngestionStatus, RunType
from lifeops_core.repositories.ingestion_runs import IngestionRunRepository
from lifeops_core.repositories.manual_daily_logs import ManualDailyLogRepository
from lifeops_core.repositories.users import UserRepository
from lifeops_core.schemas import DailyLogCreate
from lifeops_core.storage.bronze import BronzeStorage
from lifeops_core.storage.object_store import MinioObjectStore
from lifeops_core.timeutils import ReportingClock, utc_day_bounds

logger = logging.getLogger("generate_sample_data")

CATEGORIES = [
    ("groceries", 45_000, 280_000),
    ("coffee", 25_000, 65_000),
    ("transport", 15_000, 90_000),
    ("dining", 80_000, 450_000),
    ("subscriptions", 59_000, 599_000),
    ("fitness", 0, 0),  # chance-driven below
    ("gaming", 200_000, 1_200_000),
]
PAYMENT_METHODS = ["cash", "card", "bank-transfer", "wallet"]
NOTES = [
    "Long deep-work block after lunch.",
    "Roadmap session with the thesis project — felt good.",
    "Slow start, recovered in the evening.",
    "Full rest day, read a bit, slept early.",
    "Soccer practice, legs still sore.",
    "Studied system design instead of gaming.",
    "Watched too much, slept late.",
]
TAG_SETS = [
    ["deep-work"],
    ["study", "thesis"],
    ["gym"],
    ["cardio", "soccer"],
    ["rest"],
    ["family"],
    ["side-project", "lifeops"],
    ["study"],
]


def _rand_minutes(rng: random.Random, chance: float, minimum: int, maximum: int) -> int | None:
    return rng.randint(minimum, maximum) if rng.random() < chance else None


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_daily_log(rng: random.Random, day: date, clock: ReportingClock) -> DailyLogCreate:
    weekday = day.weekday()  # 0=Mon ... 6=Sun
    work_day = weekday < 5
    coding = rng.uniform(2.5, 6.5) if work_day else rng.uniform(0.0, 3.0)
    study = rng.uniform(0.0, 2.0) if work_day else rng.uniform(0.5, 4.0)
    sleep = rng.gauss(7.0, 0.8)
    sleep = min(max(sleep, 5.0), 9.8)
    mood = 1 + int(min(max((sleep - 5.0) / 1.5, 0.0), 1) * 2.4 + rng.random() * 2.2)
    mood = min(max(mood, 1), 5)
    workout = _rand_minutes(rng, 0.45 if work_day else 0.7, 20, 45)
    soccer = _rand_minutes(rng, 0.30, 30, 90)
    tags = list(rng.choice(TAG_SETS))
    notes = rng.choice(NOTES)
    return DailyLogCreate(
        log_date=day,
        sleep_hours=round(sleep, 2),
        mood_score=mood,
        study_hours=round(study, 2),
        coding_hours=round(coding, 2),
        workout_minutes=workout,
        soccer_minutes=soccer,
        notes=notes,
        tags=tags,
    )


def github_payload(rng: random.Random, day: date) -> dict:
    """Shaped like the GitHub REST commits response for a day."""
    volume = 0 if rng.random() < 0.25 else rng.randint(1, 9 if day.weekday() < 5 else 4)
    commits = []
    for _i in range(volume):
        hour = 1 if day.weekday() < 5 else 9  # UTC 01:00 ≈ 08:00 UTC+7
        ts = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), tzinfo=UTC)
        commits.append(
            {
                "sha": "".join(rng.choice("0123456789abcdef") for _ in range(40)),
                "commit": {
                    "author": {
                        "name": "Life Owner",
                        "email": "owner@lifeops.local",
                        "date": _iso(ts),
                    },
                    "message": rng.choice(
                        [
                            "fix: daily log upsert edge case",
                            "feat: silver layer dedup keys",
                            "chore: dbt tests",
                            "refactor: repository pattern",
                            "test: incremental sync",
                            "docs: engineering decisions",
                        ]
                    ),
                },
                "repo_name": rng.choice(["lifeops", "garage-management", "thesis-notes"]),
            }
        )
    return {"kind": "github_commits", "items": commits, "fetch_date": day.isoformat()}


def calendar_payload(rng: random.Random, day: date) -> dict:
    n_events = 0 if rng.random() < 0.3 else rng.randint(1, 5)
    items = [
        {
            "kind": "calendar#event",
            "summary": rng.choice(
                [
                    "Thesis focus block",
                    "Standup",
                    "Study group",
                    "Class: Networks",
                    "Dinner w/ friends",
                    "Gym",
                ]
            ),
            "start": _iso(
                datetime(day.year, day.month, day.day, 2, rng.randint(0, 45), tzinfo=UTC)
            ),
            "end": _iso(datetime(day.year, day.month, day.day, 4, rng.randint(0, 45), tzinfo=UTC)),
            "calendar_name": rng.choice(["Personal", "Work", "Study"]),
        }
        for _ in range(n_events)
    ]
    return {"kind": "calendar_events", "items": items, "fetch_date": day.isoformat()}


def spotify_payload(rng: random.Random, day: date) -> dict:
    artists = [
        "Daft Punk",
        "Ólafur Arnalds",
        "Emancipator",
        "LOFI beats",
        "Ólafur Arnalds",
        "Phum Viphurit",
    ]
    items = [
        {
            "track": {
                "name": "Deep Work mix",
                "artists": [{"name": rng.choice(artists)}],
                "album": {
                    "name": rng.choice(["Discovery", "Re:member", "Dusk to Dawn", "Morning Coffee"])
                },
                "duration_ms": rng.randint(120_000, 380_000),
            },
            "played_at": _iso(
                datetime(
                    day.year, day.month, day.day, rng.randint(0, 15), rng.randint(0, 59), tzinfo=UTC
                )
            ),
        }
        for _ in range(rng.randint(0, 30))
    ]
    return {"kind": "spotify_recently_played", "items": items, "fetch_date": day.isoformat()}


def weather_payload(rng: random.Random, day: date) -> dict:
    return {
        "kind": "weather_daily",
        "fetch_date": day.isoformat(),
        "location": {"lat": 10.8231, "lon": 106.6297, "name": "Ho Chi Minh City"},
        "daily": {
            "time": [day.isoformat()],
            "temperature_max": [round(rng.uniform(29.0, 37.0), 1)],
            "temperature_min": [round(rng.uniform(22.0, 27.0), 1)],
            "rain_sum": [round(rng.uniform(0.0, 80.0), 1)],
            "air_quality_index": [rng.randint(20, 180)],
        },
    }


def generate(args: argparse.Namespace) -> dict:
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    clock = ReportingClock.from_settings(settings)

    engine = create_pg_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    object_store = MinioObjectStore.from_settings(settings)

    rng = random.Random(args.seed)
    today = clock.today()

    with session_factory() as session:
        user = UserRepository(session).ensure_default_user(settings)
        logger.info("Seeding as user %s (%s)", user.id, user.email)

        logs_repo = ManualDailyLogRepository(session)
        runs_repo = IngestionRunRepository(session)

        bronze = BronzeStorage(object_store, session_factory)
        object_store.ensure_bucket()

        counts = {"logs": 0, "expenses": 0, "runs": 0, "bronze": 0}

        for offset in range(args.days, 0, -1):
            day = today - timedelta(days=offset)
            day_log = generate_daily_log(rng, day, clock)
            logs_repo.upsert(user.id, day_log)
            session.commit()
            counts["logs"] += 1

            # --- expenses: 0-3 daily + one monthly rent anchor ---
            for _ in range(rng.randint(0, 3)):
                good = rng.choice(CATEGORIES)
                big = rng.random() < 0.02
                amount = rng.randint(2_500_000, 4_500_000) if big else rng.randint(good[1], good[2])
                if amount <= 0:
                    continue
                session.add(
                    Expense(
                        user_id=user.id,
                        expense_date=day,
                        amount=amount,
                        currency="VND",
                        category=good[0],
                        payment_method=rng.choice(PAYMENT_METHODS),
                        description=None,
                    )
                )
                session.commit()
                counts["expenses"] += 1

            # --- ingestion runs + bronze payloads per source ---
            window_start, window_end = utc_day_bounds(day)
            source_jobs: list[tuple[str, str, dict]] = [
                ("manual_logs", "daily_logs", {"daily_log": day_log.model_dump(mode="json")}),
                ("github", "commits", github_payload(rng, day)),
                ("calendar", "events", calendar_payload(rng, day)),
                ("spotify", "recently_played", spotify_payload(rng, day)),
                ("weather", "daily", weather_payload(rng, day)),
            ]
            for source, dataset, payload in source_jobs:
                stamp = datetime.combine(
                    day, time(rng.randint(0, 15), rng.randint(0, 59)), tzinfo=UTC
                )
                failed = rng.random() < 0.02  # 2% failed runs → dashboard alert realism
                run = runs_repo.create(
                    user_id=user.id,
                    source_name=source,
                    run_type=RunType.SCHEDULED,
                    window_start=window_start,
                    window_end=window_end,
                    trigger="demo_scheduler",
                    started_at=stamp,
                )
                session.commit()  # run row must exist before bronze references it
                if failed:
                    runs_repo.mark_failed(run, "demo failure: simulated extractor error")
                    session.commit()
                    counts["runs"] += 1
                    continue
                results = bronze.write_batch(
                    source_name=source,
                    dataset=dataset,
                    payloads=[payload],
                    ingestion_run_id=run.id,
                    user_id=user.id,
                    window_start=window_start,
                    window_end=window_end,
                    ingested_at=stamp,
                    attributes={"demo_generated": True},
                )
                run.records_extracted = len(results)
                run.records_loaded = len(results)
                run.status = IngestionStatus.SUCCESS.value
                run.finished_at = stamp + timedelta(minutes=2)
                session.commit()
                counts["runs"] += 1
                counts["bronze"] += len(results)

        session.commit()

    summary = {"estimated_rows": counts, "days": args.days, "seed": args.seed}
    logger.info("Seeded: %s", json.dumps(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LifeOps demo data (no external APIs).")
    parser.add_argument("--days", type=int, default=90, help="Days of history (default 90)")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    args = parser.parse_args()
    summary = generate(args)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
