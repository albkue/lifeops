# LifeOps — Architecture

> Status: Phase 1 complete (core stack + manual log + Bronze). Phases 3-12 evolve this
> document incrementally; what is written here is implemented, not aspirational —
> aspirational items live in `README.md > Features`.

## The big picture

```
            ┌──────────────────────────────────────────────────────┐
            │                     SOURCES                          │
            │  manual daily log (mobile-friendly POST)             │
            │  github / calendar / spotify / weather (Phase 6/7/11) │
            └──────────────┬───────────────────────────────────────┘
                           │ extractors (incremental cursors) + Dagster schedules (Phase 3)
                           ▼
            ┌──────────────────────────────┐
            │ ingestion-api (FastAPI :8000) │──bronze──►  object store :9000
            │  CRUD · run triggers · health │            (v1: SeaweedFS; MinIO-swappable)
            └──────────┬───────────────────┘
                       │
        Bronze  (raw JSON, immutable, keyed by sha8; ledger row in Postgres)
                       │  Silver transforms (Phase 4: Parquet, DuckDB/Polars)
                       ▼
        Silver  (cleaned, deduped, UTC-normalized typed datasets)
                       │  dbt (Phase 5)
                       ▼
        Gold    (PostgreSQL star schema: dim_* / fct_* / agg_*)
                       │
        ┌───────────────┴────────────────┐
        ▼                                ▼
 insights-api (:8001)             Next.js dashboard (Phase 9)
 weekly Life Report, balance      today/week/month views, pipeline health
 score, anomaly alerts (Phase 10)
 ```

## Layers and their owners (Phase 1)

| Concern | Module | Notes |
|---|---|---|
| Settings | `lifeops_core.config` | Pydantic-settings, explicit env aliases |
| Time invariants | `lifeops_core.timeutils` | UTC storage; UTC+7 day boundaries |
| Domain errors | `lifeops_core.domain_errors` | → HTTP mapping in `lifeops_core.api` |
| SQLAlchemy models | `lifeops_core.models` | 11 tables, UUID PKs, timestamps |
| Repositories | `lifeops_core.repositories` | No commits inside; services commit |
| Storage | `lifeops_core.storage` | S3 client + Bronze writer (idempotent) |
| Source registry | `lifeops_core.sources` | Adapters land Phase 6+ |
| Ingestion service | `services/ingestion_api/ingestion_app` | logs + runs + health + metrics |
| Insights service | `services/insights_api/insights_app` | skeleton + health (Phase 8 builds on it) |
| Demo data | `scripts/generate_sample_data.py` | No external APIs; writes Bronze like an extractor |

## Medallion residency

- **Bronze (`bronze/{source}/{dataset}/extr_date=YYYY-MM-DD/ingested_at=.../{sha8}-{ulid}.json`)**:
  Stored layout: `{"payload": <source data>, "_lifeops_meta": {ingested_at, source,
  dataset, schema_version, extraction_window_*}}`. The source data is preserved
  verbatim under a collision-free key; nothing is re-shaped at this layer. Hive-style
  path partitioning makes Bronze readable by DuckDB/Polars/Spark directly.
- **Bronze ledger (`raw_source_objects`)**: uniqueness on
  `(source, dataset, payload_sha256, extraction_window_start)` — the dedupe digest is
  computed over the *payload only* (never the envelope), so retries and re-submissions
  are true no-ops and replays are idempotent.
- **Silver / Gold**: arrive in Phases 4 and 5 respectively; Bronze is intentionally
  already shaped for that transition.

## Key invariants

1. All timestamps stored in UTC (`timestamptz`), aware datetimes everywhere in Python.
2. "Today" and report windows are computed in `LIFEOPS_TIMEZONE` (UTC+7), never from
   server-local time.
3. Route handlers contain no business logic; services raise `DomainError` subclasses,
   mapped centrally to HTTP.
4. Repositories never commit; services own transaction boundaries.
5. Secrets live only in `.env`/container env; never in the DB, never in code.
6. Every daily-log write is mirrored to Bronze *best-effort* — MinIO being down must
   never block manual logging; the warehouse row is the source of truth for app state.
