# LifeOps — Personal Data Lakehouse

> A local-first personal analytics platform: ingest my own tools, store everything in a
> medallion lakehouse, and answer real questions like *"how much focused work did I really
> do this week?"*, *"is my study/work/fitness balance healthy?"*, and *"which data source
> stopped updating?"* — producing a weekly **Life Report** and a live daily dashboard.

---

## Problem statement

I live across GitHub, Google Calendar, a gym, a school schedule, Spotify, and personal
finances — but my data lives in six disconnected apps that produce numbers, not answers.
LifeOps is a personal data platform that:

1. **Ingests** each tool's data (official APIs where available; manual logging where not)
   incrementally and idempotently,
2. **Stores** the exact raw payloads immutably (Bronze), cleans them into typed datasets
   (Silver), and models them with dbt into analytics tables (Gold),
3. **Delivers** a daily dashboard, a weekly Life Report, a configurable Life Balance Score,
   and proactive anomaly alerts when data goes stale or results go bad.

## Architecture

```
                ┌─────────────────────────────────────────────────────────────┐
                │                        SOURCES (optional)                   │
                │  Manual daily log · GitHub · Calendar · Spotify · Expenses   │
                │  Weather (open-meteo)          (OAuth逐步: Phase 6/7/11)     │
                └───────┬──────────────────────────────┬──────────────────────┘
                        │ extractors (incremental)      │
                ┌───────▼─────────┐          ┌──────────▼───────────┐
                │  ingestion-api  │          │  Dagster scheduler   │
                │  FastAPI :8000  │          │  (Phase 3, :3001)    │
                └───────┬─────────┘          └──────────▲───────────┘
                        │ Bronze: raw JSON, immutable    │ runs jobs
                        ▼                                │
                ┌─────────────────────────────────────────────┐
                │ MinIO :9000 (S3 API)                        │
                │  bronze/{github|calendar|spotify|weather|    │
                │          manual_logs|expenses}/dataset/...  │
                │  silver/ (Parquet)   gold/ (Phase 4+)       │
                └──────────────────────┬──────────────────────┘
                                       │ dbt models + tests
                ┌──────────────────────▼──────────────────────┐
                │ PostgreSQL :5433 (warehouse + app DB)       │
                │  users · ingestion_runs · manual_daily_logs │
                │  expenses · alerts · report_snapshots …     │
                │  gold: dim_* · fct_* · agg_*  (Phase 5+)    │
                └──────────┬────────────────────┬─────────────┘
                           │                    │
                ┌──────────▼─────────┐ ┌────────▼──────────┐
                │  insights-api      │ │  Next.js dashboard│
                │  FastAPI :8001     │ │  (Phase 9)        │
                │  reports/alerts    │ │  dark, mobile     │
                └────────────────────┘ └───────────────────┘
```

**Short version:** raw API responses land in MinIO (Bronze), get cleaned into Parquet
(Silver), then dbt builds star-schema Gold tables in PostgreSQL that power the dashboard,
the Insights API, the weekly Life Report, and the alerting engine.

## Tech stack

| Concern       | Choice                                                     |
|---------------|-------------------------------------------------------------|
| Language      | Python 3.11+ (typed, Pydantic v2, SQLAlchemy 2, ruff + mypy) |
| APIs          | FastAPI (ingestion-api :8000, insights-api :8001)            |
| Warehouse/DB  | PostgreSQL 16 (SQLAlchemy + Alembic migrations)              |
| Object lake   | MinIO, S3 API (raw JSON Bronze; Parquet Silver/Gold)         |
| Analytics     | DuckDB near Bronze/Silver (ad-hoc exploration), dbt for Gold |
| Transforms    | dbt Core (staging → intermediate → marts, tests, docs)       |
| Orchestration | **Dagster** (Phase 3) — see docs/engineering_decisions.md    |
| Dashboard     | **Next.js** (Phase 9) — see docs/engineering_decisions.md    |
| Tests / CI    | pytest (+ testcontainers) · ruff · mypy · GitHub Actions     |

## Features

- ✅ **Phase 1**: repo scaffold, Docker Compose core stack (Postgres + object store +
  2 FastAPI services), full PostgreSQL schema + Alembic migrations, manual daily
  log API (mobile-friendly upsert), Bronze raw-store writer with SHA-256 idempotency
  ledger, sample data generator + demo seeder, tests + CI.
- ✅ **Phase 2**: Bronze integrity audit (`POST /ingestion/{source}/audit`,
  `scripts/audit_bronze.py`), Bronze ledger catalog (`GET /ingestion/objects`),
  window-overlap filters on runs, CI migration-parity step (`alembic upgrade head` in
  Actions), testcontainers degradation hardening.
- ⏳ Phase 3: Dagster orchestration & schedules (next).
- Phase 4: Silver Parquet layer (dedup, UTC-normalized, typed datasets in object store).
- Phase 5: dbt Gold layer (dim/fct/agg marts + dbt tests) → `make dbt-run`.
- Phase 6/7: GitHub + Google Calendar extractors (OAuth, incremental cursors).
- Phase 8: Weekly Life Report + insights API over Gold marts.
- Phase 9: Next.js dashboard.
- Phase 10: Life Balance Score + anomaly alerts (pluggable channels).
- Phase 11: Spotify, weather, expenses ingestion.
- Phase 12: docs refinement, demo hardening.

## Local setup

### Prerequisites

- Docker Desktop, GNU make (Git Bash/WSL on Windows), Python 3.11+
- 2026 note: **MinIO's images are login-gated.** If `docker compose up` fails to pull
  MinIO:
  - `docker login quay.io` with a MinIO account, **or**
  - run MinIO natively (free server binary from dl.min.io) and set
    `MINIO_ENDPOINT=host.docker.internal:9000` in `.env` — see `docs/demo.md`.

### Quick start

```bash
cp .env.example .env    # then edit (see Environment variables below)

docker compose up -d           # postgres + minio + migrate + ingestion-api + insights-api
docker compose ps              # everything healthy?
open http://localhost:8000/docs   # ingestion API OpenAPI
open http://localhost:8001/docs   # insights API OpenAPI
```

### Demo data (works without any real API credentials)

```bash
make seed-demo        # 90 days of deterministic habits/expenses/bronze payloads
# or: docker compose run --rm ingestion-api python scripts/seed_demo_data.py --days 90
```

### Docker Compose commands

```bash
docker compose up -d            # start everything
docker compose logs -f          # tail logs
docker compose down             # stop
docker compose run --rm migrate # alembic upgrade head
docker compose run --rm tests   # pytest against the compose services
docker compose restart ingestion-api
```

## Environment variables

See `.env.example` (self-documented). Highlights:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL; container uses `@postgres:5432`, host scripts use `@localhost:5433` |
| `POSTGRES_*` | Postgres container credentials / host port |
| `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` | Bronze object store |
| `LIFEOPS_TIMEZONE` | Day-boundary reporting timezone (default `Asia/Ho_Chi_Minh`, UTC+7) |
| `GITHUB_TOKEN`, `GOOGLE_*`, `SPOTIFY_*` | Optional source credentials — all empty by default |

Secrets never leave `.env` (gitignored); empty optional variables simply disable a source.

## API examples

```bash
# log today's habits (upsert — safe to re-submit)
curl -X POST http://localhost:8000/api/v1/logs/daily \
  -H 'Content-Type: application/json' \
  -d '{"log_date": "2026-11-10", "sleep_hours": 7.5, "mood_score": 4,
       "study_hours": 2, "coding_hours": 5, "workout_minutes": 30,
       "soccer_minutes": 0, "notes": "deep work", "tags": ["deep-work"]}'

GET  /api/v1/logs/daily?start_date=2026-11-01&end_date=2026-11-30   # range (paginated)
GET  /api/v1/logs/daily/by-date/2026-11-10
PATCH /api/v1/logs/daily/{id}      # explicit field override
DELETE /api/v1/logs/daily/{id}

POST /api/v1/ingestion/github/run        # 501 until Phase 6 (adapter registry known)
POST /api/v1/ingestion/github/backfill   # body: {"window_start": ..., "window_end": ...}
GET  /api/v1/ingestion/runs              # pipeline health page
GET  /api/v1/ingestion/sources           # discovery
GET  /api/v1/ingestion/runs?source=github&status=failed

GET  /api/v1/health      # DB is critical (503 when down); MinIO degrades only
GET  /api/v1/metrics     # counts + latest run per source
```

All errors return a structured `{ "error", "message", "details", "service" }` body with
correct HTTP codes. OpenAPI docs: `http://localhost:8000/docs`.

## dbt commands

dbt lands with Phase 5; until then `make dbt-run` prints the roadmap. Once Phase 5
merges:

```bash
make dbt-run      # dbt build (models + tests)
make dbt-test     # dbt test only
dbt run --project-dir dbt --profiles-dir dbt   # raw form
```

## Bronze operations (Phase 2)

```bash
# integrity audit via CLI (exit code 0 = clean, 1 = problems)
docker compose run --rm ingestion-api python scripts/audit_bronze.py --source github

# same via API (window optional)
curl -s -X POST 'http://localhost:8000/api/v1/ingestion/github/audit?dataset=commits' \
  -d '{"window_start": "2026-11-01T00:00:00Z", "window_end": "2026-11-09T00:00:00Z"}'

# raw-data catalog (what the dashboard's freshness page will consume)
curl -s 'http://localhost:8000/api/v1/ingestion/objects?source_name=github&limit=10'
```

## Dashboard screenshots

> _Placeholder — Phase 9. Once the Next.js dashboard lands:_
> ![Today view](docs/img/dashboard-today.png)
> ![Weekly view](docs/img/dashboard-week.png)
> ![Pipeline health](docs/img/dashboard-pipeline.png)

## Testing & CI

```bash
make test          # pytest inside Docker (compose Postgres + object store)
make test-unit     # pure unit tests only
make check         # ruff + mypy (CI parity)
```

Unit tests run everywhere; integration tests find Postgres/S3 via:

1. `TEST_DATABASE_URL` + `TEST_MINIO_ENDPOINT` (compose/CI), or
2. spinning **testcontainers** automatically, or
3. skipping gracefully when neither is available (Bronze mirror tests degrade or skip).

GitHub Actions runs lint (ruff), type check (mypy), an `alembic upgrade head`
migration-parity step, pytest (against real Postgres + SeaweedFS service containers),
then builds both service images; it fails on any error.

## Roadmap

See **Features** above for the phase-by-phase plan; the detailed per-phase notes live in
`docs/` (`architecture.md`, `data_model.md`, `api.md`, `demo.md`).

## Engineering decisions (summary)

Full rationale in `docs/engineering_decisions.md`; the headline choices:

- **Medallion architecture** — one contract ("chain of custody"): raw immutable Bronze →
  cleaned typed Silver → modeled Gold. Re-processing a layer never re-calls an API.
- **Raw JSON first** — schemas change; the truth of what an API returned on day N doesn't.
- **Parquet for Silver/Gold** — columnar, typed, cheap in object storage, trivially
  consumed by DuckDB/Polars/Spark later.
- **dbt for Gold** — SQL transformations that an analyst-DIY stack (this project) can
  audit, test, and document; DAG dependency discipline for free.
- **PostgreSQL as warehouse** — at one user's data volume, Postgres + dbt is *the* right
  warehouse until it demonstrably isn't (documented scale-out criteria).
- **Dagster over Airflow** — asset graph ≈ medallion layers; lighter and testable.
- **UTC everywhere, day boundaries in UTC+7** — storage invariant vs. human meaning.
- **Single seeded user, no auth (v1)** — schema carries `user_id` FKs from day one, so
  multi-user is a seam, not a migration crisis.

## Future improvements

- Event-driven ingestion via Kafka (only if schedules prove insufficient — deliberately
  deferred, per constraints).
- Gold-layer caching + materialized views for the dashboard.
- Mobile-friendly PWA for the manual log page.
- Encrypted-at-rest OAuth token storage (needs a decision in Phase 6 — tracked).
- Multi-user mode (a real auth service, RLS-based row isolation).
