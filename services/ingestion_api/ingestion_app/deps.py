"""FastAPI dependency providers (all state lives on `request.app.state`)."""

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from lifeops_core.config import Settings
from lifeops_core.models import User
from lifeops_core.repositories.users import UserRepository
from lifeops_core.storage.bronze import BronzeStorage
from lifeops_core.storage.object_store import MinioObjectStore
from lifeops_core.timeutils import ReportingClock


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_object_store(request: Request) -> MinioObjectStore:
    return request.app.state.object_store


def get_bronze_storage(request: Request) -> BronzeStorage:
    return request.app.state.bronze_storage


def get_reporting_clock(request: Request) -> ReportingClock:
    return request.app.state.clock


def get_current_user(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    """Single-user deployment (v1): resolve (or lazily create) the default user.

    When multi-auth arrives, this is the single seam that changes.
    """
    return UserRepository(session).ensure_default_user(settings)
