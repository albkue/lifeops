"""LifeOps Ingestion API service entrypoint.

Owns: manual daily logs, ingestion triggers + status, health/metrics.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from lifeops_core.api import register_error_handlers
from lifeops_core.config import Settings, get_settings
from lifeops_core.db.session import create_pg_engine, make_session_factory
from lifeops_core.logging_setup import configure_logging
from lifeops_core.storage.bronze import BronzeStorage
from lifeops_core.storage.object_store import MinioObjectStore
from lifeops_core.timeutils import ReportingClock

SERVICE = "ingestion-api"

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "[%s] starting (env=%s tz=%s)", SERVICE, settings.environment, settings.timezone_name
        )
        yield
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="LifeOps Ingestion API",
        version="0.1.0",
        description=(
            "LifeOps Personal Data Lakehouse. Manual daily-log CRUD, ingestion "
            "runs, and Bronze raw-store mirroring. Insights live on :8001."
        ),
        lifespan=lifespan,
    )

    engine = create_pg_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    object_store = MinioObjectStore.from_settings(settings)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.object_store = object_store
    app.state.bronze_storage = BronzeStorage(object_store, session_factory)
    app.state.clock = ReportingClock.from_settings(settings)
    app.state.service_name = SERVICE
    app.state.version = app.version

    # Declared-then-included routers keep route tables ordered for OpenAPI.
    from ingestion_app.routers.health import router as health_router
    from ingestion_app.routers.ingestion import router as ingestion_router
    from ingestion_app.routers.logs import router as logs_router
    from ingestion_app.routers.metrics import router as metrics_router

    app.include_router(health_router)
    app.include_router(logs_router)
    app.include_router(ingestion_router)
    app.include_router(metrics_router)

    register_error_handlers(app, service=SERVICE)
    return app


app = create_app()
