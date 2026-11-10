"""Small DB inspector used during dev; safe to run from host or container."""

from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://lifeops:lifeops@localhost:5433/lifeops")
with engine.connect() as conn:
    print("alembic_version:", list(conn.execute(text("select version_num from alembic_version"))))
    rows = conn.execute(
        text("select tablename from pg_tables where schemaname='public' order by 1")
    )
    print("tables:", [r[0] for r in rows])
engine.dispose()
