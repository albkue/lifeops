# LifeOps — Naming conventions (locked with the user, Phase 1)

Agreed conventions; PRs that violate these fail review.

## Object-store paths

```
bronze/{source}/{dataset}/extr_date=YYYY-MM-DD/ingested_at=YYYYMMDDTHHMMSSZ/{sha8}-{ulid12}.json
silver/{domain}/{dataset}/...      (Phase 4)
```

- Sources: `github`, `calendar`, `spotify`, `weather`, `manual_logs`, `expenses`
- Datasets: `commits`, `pull_requests`, `events`, `recently_played`, `daily`,
  `daily_logs`, `transactions`
- Hive-style `key=value` segments (DuckDB/Polars/Spark can filter with partition pushdown)

## dbt

- Staging: `staging_{source}__{dataset}` (e.g. `staging_github__commits`)
- Intermediate: `int_{domain}__{purpose}` (e.g. `int_habit__daily_base`)
- Marts: `dim_`, `fct_`, `agg_` exactly as listed in the repo structure
- Tests ≥ everything: unique `natural_key`, not-null FK columns, business rules

## PostgreSQL

- snake_case, plural table names (`users`, `manual_daily_logs`)
- UUID PKs; `created_at`/`updated_at` everywhere justified
- Config in `pipeline_config` (key/value JSONB) rather than new tables per knob
- CHECK constraints named `ck_{table}_{constraint}`, FKs
  `fk_{table}_{column}_{ref_table}`, uniques `uq_{table}_{cols}` (Alembic naming
  convention in `lifeops_core/db/base.py`)

## Python

- Services: `services/{name}/{name}_app/` (package name unique repo-wide so mypy/uv
  never brag); thin routers, services hold logic, repos hold SQL
- Env vars: `DATABASE_URL`/`MINIO_*` (infra conventions) + `LIFEOPS_*` (product flags)
- One shared kernel: `lifeops_core.*` (models, repos, storage, config, time, errors)
