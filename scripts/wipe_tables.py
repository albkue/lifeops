"""Wipe all lifeops tables (dev helper for re-seeding)."""

from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://lifeops:lifeops@localhost:5433/lifeops")
tables = [
    "raw_source_objects",
    "ingestion_errors",
    "ingestion_runs",
    "manual_daily_logs",
    "expenses",
    "report_snapshots",
    "alerts",
    "notification_channels",
    "pipeline_config",
    "source_connections",
    "users",
]
with engine.begin() as conn:
    stmt = "TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"
    conn.execute(text(stmt))
print("wiped")
engine.dispose()
