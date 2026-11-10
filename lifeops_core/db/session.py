"""Engine + session factory builders (sync SQLAlchemy / psycopg3)."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_pg_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
