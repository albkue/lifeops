# LifeOps — Engineering decisions

Status-kept-current per phase. Each row states the decision and the reasoning that can
be reopened if the constraint changes.

## Set in Phase 1 (with the user)

| Decision | Why |
|---|---|
| **Orchestrator: Dagster** (Phase 3) | Asset graph maps 1:1 to medallion layers; small footprint; trivially testable (`build_asset_job`); `dagster-dbt` ties Gold-building to assets cleanly. Airflow chosen over only when resume signaling beats real fit: it costs ~8 containers and heavy opinionated complexity for a single-user product. |
| **Dashboard: Next.js** (Phase 9) | Chosen over Streamlit for full design control (dark-mode-first, mobile responsive); the maintenance cost is accepted deliberately by the owner. Streamlit remains the fallback if Phase 9 velocity matters more than polish. |
| **Single user, no auth (v1)** | Local-first product. Every fact table carries `user_id` FK from day one, so multi-user is a seam (a real auth service + row-level security), not a migration crisis. |
| **Day boundary = UTC+7** (`Asia/Ho_Chi_Minh`) | All storage UTC; day boundaries ("today", week start, report windows) computed via `ReportingClock` in the configured zone. Timezone lives in `LIFEOPS_TIMEZONE`; changing it is a config change, not code. |
| **Naming** | Exactly the user's architecture: paths like `bronze/github/commits/`, dbt prefixes `staging_/int_/fct_/dim_/agg_`, snake_case plural tables — codified in `docs/naming.md`. |

## Architectural decisions

**Why a medallion architecture?**
Because re-processing is inevitable (you WILL re-parse the calendar source six months
from now). With medallion layers, each layer has a single contract → re-running a layer
downstream never re-calls an upstream API. Bronze→Silver is cheap (data already local);
Silver→Gold is cheap (sources cleaned and stable). This localizes blast radius of bugs
to the layer that produced them.

**Why store raw JSON before transformation?**
Original API payloads are ground truth of *what the API returned*, which is needed for
(1) replay/backfill after a schema change, (2) debugging silver/gold logic against real
responses without re-hitting rate limits/OAuth, (3) auditing where a bad value came from
when gold numbers look wrong. The Bronze object layout keeps the source payload
verbatim under `payload` and metadata under `_lifeops_meta`, so even curl-reading the
bucket is understandable months later.

**Why Parquet for Silver/Gold files?**
Columnar compression (day-level gzip ~10-40x on JSON), schema-aware (type drift happens
loudly, not silently), and universally consumable (DuckDB reads it with one line; this
stack stays dbt + Polars-ready without SaaS).

**Why dbt (over raw SQL/Airflow transforms)?**
Tests belong to transformations, not extra scripts. dbt gives declarative data tests
(uniqueness, relationships, refusal of negative durations), documentation with lineage,
and one SQL style across the team (this project = future-you). `make dbt-run` wraps
`dbt build` (models + tests) in one shot.

**Why PostgreSQL as warehouse?**
Volume honestly fits (90 days → hundreds of rows/day). Postgres buys: one engine for
app + marts, real enums/CHECK constraints, JSONB fallback for late-binding fields, and
a path to partitioning when needed. Move-out criteria (documented, revisit at Phase 8):
single fact table > 10M rows, dashboard query P95 > 2s at Phase-9 scale, or
larger-than-RAM aggregations beyond dbt-native incremental models.

**How incremental ingestion works**
`source_connections.cursor` (JSONB) stores the per-source watermark (updated_at,
page-token, or both). Extractors (Phase 6+) pull the cursor, request a window, write
Bronze rows, and persist the max cursor + `last_sync_at`. Backfill is the same code
path with an explicit window and idempotent Bronze dedupe via the sha ledger.

**How deduplication works**
Three rules, by layer:
1. *Bronze*: unique ledger key = (source, dataset, payload_sha256, extraction_window).
   The digest is over payload ONLY (never ingestion metadata), so re-runs are no-ops.
2. *Silver*: natural keys (e.g. manual_logs: (user_id, log_date)) — last-write-wins or
   merge semantics defined per source (documented per silver model in Phase 4).
3. *Gold*: dbt incremental models with unique keys (e.g. `fct_daily_habits` per date),
   guarded by dbt tests (duplicate-date test).

**How late / missing data is handled**
Windows are half-open and backfill-able (explicit POST `/ingestion/{s}/backfill` with a
window). Gold models compute over configurable lookback (e.g. weekly report recomputed
from Silver for N back-days), so a late GitHub commit is picked up on the next
Silver/Gold rebuild. Trailing-quiet windows (e.g. "yesterday may still trickle") are
marked in the freshness alerts rather than treated as failures (Phase 10).

**How secrets are protected**
`.env` (gitignored) / container env only. DB never stores raw credentials in v1; when
OAuth arrives (Phase 6), tokens live in `source_connections.credentials` — with
at-rest encryption being a tracked decision for that phase (warrants an explicit task,
not silent JSONB).

**How the system scales later**
Single-user on one machine: compose with volume storage; ~360 Bronze objects/90 days.
Moving out means: Postgres vertical scale first, then read-replica for the dashboard
(transparent — all apps share one `lifeops_core.db` engine layer); Bronze/Parquet files
are already cloud-portable (S3-compatible, hive-partitioned); Dagster jobs scale via
the standard executor options. None of the heavy tools (Spark, Kafka, K8s) enter until
a number justifies them.

**Change history review · What changes in a multi-user production deployment**
- Auth: the single seam is `get_current_user` in `app/deps.py`; a real OIDC provider
  replaces it; every table is ready (user_id FKs everywhere).
- Postgres: add row-level security policies per user instead of per-table FK filters in
  app code (belt-and-braces).
- Secrets: move to a secret manager; `source_connections.credentials` becomes
  encrypted envelope (per-user key).
- Ingestion: Dagster daemon runs on a fleet or serverless; OAuth refresh jobs become
  background-safe (dedup via cursor).
- Object store: switch bucket prefix per user; MinIO→cloud S3 flip is one env var.

**Phase-1-environment note (2026-11-10): MinIO images gated**
MinIO's official Docker images now require quay.io login and the AIStor native binary
requires even a free trial license. Decision: v1 runs **SeaweedFS** (Apache 2.0,
S3-compatible) at the same hostname via `MINIO_IMAGE` — the whole storage/bronze code
client remains S3-generic, so swapping to a licensed MinIO is a one-variable change.
Behavior verified in tests + demo seed (docker compose up, 42 tests, 443 bronze
objects).
