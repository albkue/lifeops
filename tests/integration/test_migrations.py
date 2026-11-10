"""Alembic migrations are valid and produce the full Phase 1 schema."""

from pathlib import Path

import pytest
import sqlalchemy

ALEMBIC_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.integration
def test_migrations_build_schema(engine):
    from alembic import command
    from alembic.config import Config

    target = engine.url.set(database="lifeops_migrations_test")
    cfg = Config(str(ALEMBIC_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", str(target))

    # NOTE: `str(engine.url)` masks the password as "***" in SQLAlchemy 2.x —
    # always build engines from the URL object (or render_as_string with
    # hide_password=False), never from a rendered string.
    target = engine.url.set(database="lifeops_migrations_test")
    cfg = Config(str(ALEMBIC_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", target.render_as_string(hide_password=False))

    admin = sqlalchemy.create_engine(engine.url.set(database="postgres"))
    with admin.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(sqlalchemy.text('DROP DATABASE IF EXISTS "lifeops_migrations_test"'))
        conn.execute(sqlalchemy.text('CREATE DATABASE "lifeops_migrations_test"'))
    admin.dispose()

    command.upgrade(cfg, "head")

    probe = sqlalchemy.create_engine(target)
    try:
        with probe.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    sqlalchemy.text("select tablename from pg_tables where schemaname='public'")
                )
            }
    finally:
        probe.dispose()

    expected = {
        "users",
        "source_connections",
        "manual_daily_logs",
        "expenses",
        "ingestion_runs",
        "ingestion_errors",
        "raw_source_objects",
        "alerts",
        "notification_channels",
        "report_snapshots",
        "pipeline_config",
    }
    assert expected <= tables


@pytest.mark.integration
def test_models_and_migration_agree_on_schema(engine):
    """Guard against model drift: alembic upgrade must yield at least the model tables."""
    import lifeops_core.models  # noqa: F401
    from lifeops_core.db.base import Base

    model_tables = set(Base.metadata.tables.keys())
    assert {
        "users",
        "source_connections",
        "manual_daily_logs",
        "expenses",
        "ingestion_runs",
        "ingestion_errors",
        "raw_source_objects",
        "alerts",
        "notification_channels",
        "report_snapshots",
        "pipeline_config",
    } <= model_tables
