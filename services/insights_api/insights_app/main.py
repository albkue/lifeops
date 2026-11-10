"""LifeOps Insights API — Phase 1: skeleton + health/metrics.

Phase 8 adds the real product: /api/v1/insights/daily, /insights/weekly,
/reports/week/latest that read Gold marts (dbt models). The service container
already runs today so the compose stack, CI images, and health checks are
green from day one — query/domain layers land with Gold tables, not before.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from lifeops_core.api import register_error_handlers
from lifeops_core.config import Settings, get_settings
from lifeops_core.db.session import create_pg_engine, make_session_factory
from lifeops_core.logging_setup import configure_logging
from lifeops_core.storage.object_store import MinioObjectStore

SERVICE = "insights-api"

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("[%s] starting (env=%s)", SERVICE, settings.environment)
        yield
        engine = getattr(app.state, "engine", None)
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="LifeOps Insights API",
        version="0.1.0",
        description="Personal insights over LifeOps Gold marts (wired up in Phase 8).",
        lifespan=lifespan,
    )

    app.state.settings = settings
    engine = create_pg_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.object_store = MinioObjectStore.from_settings(settings)
    app.state.service_name = SERVICE
    app.state.version = app.version

    from insights_app.routers.health import router as health_router

    app.include_router(health_router)
    register_error_handlers(app, service=SERVICE)
    return app


app = create_app()
