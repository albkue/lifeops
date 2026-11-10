"""Alembic environment: sync URL from explicit config (tests/CLI) or settings.

Rule: if the Alembic Config already has `sqlalchemy.url` set programmatically
(test harness, CI scripts), that wins; otherwise we read the app settings
(DATABASE_URL env or .env). Nothing is ever hard-coded here.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import lifeops_core.models  # noqa: F401 - registers all tables on Base.metadata
from lifeops_core.config import get_settings
from lifeops_core.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def resolve_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit.replace("%", "%%")
    settings = get_settings()
    return settings.database_url.replace("%", "%%")


def run_migrations_offline() -> None:
    context.configure(
        url=resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = resolve_url()
    # engine_from_config needs the URL *present* in the section
    config.set_main_option("sqlalchemy.url", url)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
