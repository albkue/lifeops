"""Row counts per lifeops table (dev/debug helper)."""

from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://lifeops:lifeops@localhost:5433/lifeops")
with engine.connect() as conn:
    tables = [
        r[0]
        for r in conn.execute(
            text("select tablename from pg_tables where schemaname='public' order by 1")
        )
    ]
    for table in tables:
        if table == "alembic_version":
            continue
        count = conn.execute(text(f'select count(*) from "{table}"')).scalar()
        print(f"{table:28s} {count}")
engine.dispose()
