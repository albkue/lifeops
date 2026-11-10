import logging
import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("tests.conftest")

# Make repo-root imports work when running pytest from the root or IDEs, and
# expose the per-service packages (ingestion_app / insights_app) top-level.
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "ingestion_api"))
sys.path.insert(0, str(REPO_ROOT / "services" / "insights_api"))


# --------------------------------------------------------------------------
# Postgres fixture: TEST_DATABASE_URL env (compose/CI) or testcontainers.
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def pg_dsn() -> Generator[str, None, None]:
    """Compose/CI first (TEST_DATABASE_URL), else testcontainers."""
    dsn = os.environ.get("TEST_DATABASE_URL")
    if dsn:
        yield dsn
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        raise RuntimeError(
            "Postgres unavailable: set TEST_DATABASE_URL or install "
            "testcontainers[postgres] (pip install -e '.[dev]')."
        ) from exc

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        url = container.get_connection_url()
        yield url.replace("postgresql+psycopg2://", "postgresql+psycopg://")


# --------------------------------------------------------------------------
# MinIO fixture: TEST_MINIO_ENDPOINT env (compose/CI) or testcontainers.
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def minio_config():
    endpoint = os.environ.get("TEST_MINIO_ENDPOINT")
    if endpoint:
        yield {
            "endpoint": endpoint,
            "access_key": os.environ.get("TEST_MINIO_ACCESS_KEY", "lifeops"),
            "secret_key": os.environ.get("TEST_MINIO_SECRET_KEY", "lifeops-secret"),
        }
        return

    try:
        from testcontainers.minio import MinioContainer
    except ImportError:
        yield None  # tests degrade gracefully: bronze mirror becomes best-effort
        return

    try:
        with MinioContainer(
            "minio/minio:latest",
            access_key="lifeops-test",
            secret_key="lifeops-test-secret",
        ) as container:
            # Different testcontainers versions expose different method names
            config_getter = (
                getattr(container, "get_connection_config", None) or container.get_config
            )
            config = config_getter()
            yield {
                "endpoint": config["endpoint"],
                "access_key": config["access_key"],
                "secret_key": config["secret_key"],
            }
    except Exception:
        logger.warning("testcontainers MinIO unavailable; bronze-dependent tests will skip")
        yield None


# --------------------------------------------------------------------------
# Schema + fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def engine(pg_dsn):
    _ensure_database(pg_dsn)
    from lifeops_core.db.session import create_pg_engine

    engine = create_pg_engine(pg_dsn)
    yield engine
    engine.dispose()


def _ensure_database(dsn: str) -> None:
    """CREATE DATABASE when the target db does not exist yet (with retries:
    containerized Postgres occasionally rejects the first scram handshake
    while concurrent admin connections are being pooled - transient, value
    validated by the explicit psql al check)."""
    import time

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    url = make_url(dsn)
    target_db = url.database
    if target_db in ("postgres", None):
        return
    admin = create_engine(url.set(database="postgres"))
    try:
        for attempt in range(5):
            try:
                with admin.connect() as connection:
                    connection.execution_options(isolation_level="AUTOCOMMIT")
                    exists = connection.execute(
                        text("select 1 from pg_database where datname = :name"),
                        {"name": target_db},
                    ).scalar()
                    if not exists:
                        connection.execute(text(f'CREATE DATABASE "{target_db}"'))
                return
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1)
    finally:
        admin.dispose()


@pytest.fixture()
def clean_db(engine):
    """Schema created once (session); per-test truncation keeps tests fast but isolated."""
    from sqlalchemy import text

    import lifeops_core.models  # noqa: F401
    from lifeops_core.db.base import Base

    Base.metadata.create_all(engine)
    yield engine
    tables = ", ".join(f'"{table}"' for table in sorted(Base.metadata.tables.keys(), reverse=True))
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


# --------------------------------------------------------------------------
# Settings + FastAPI app
# --------------------------------------------------------------------------
TEST_BUCKET = "lifeops-test"


@pytest.fixture(scope="session")
def settings(pg_dsn, minio_config):
    from lifeops_core.config import Settings

    store = minio_config or {"endpoint": "unreachable:9000", "access_key": "x", "secret_key": "x"}
    return Settings(
        database_url=pg_dsn,
        minio_endpoint=store["endpoint"],
        minio_access_key=store["access_key"],
        minio_secret_key=store["secret_key"],
        minio_bucket=TEST_BUCKET,
        minio_secure=False,
        timezone_name="Asia/Ho_Chi_Minh",
        default_user_email="test@lifeops.local",
        default_user_display_name="Test Owner",
    )


@pytest.fixture(scope="session")
def ensure_bucket(settings, minio_config):
    if minio_config is None:
        return False
    from lifeops_core.storage.object_store import MinioObjectStore

    store = MinioObjectStore.from_settings(settings)
    store.ensure_bucket()
    return True


@pytest.fixture(scope="session")
def app(settings, engine, ensure_bucket):
    from ingestion_app.main import create_app

    return create_app(settings=settings)


@pytest.fixture()
def client(app, clean_db):
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture()
def session_factory(app, clean_db):
    return app.state.session_factory


@pytest.fixture()
def user_id(session_factory, settings):
    from lifeops_core.repositories.users import UserRepository

    with session_factory() as session:
        user = UserRepository(session).ensure_default_user(settings)
        return user.id
