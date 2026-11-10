# LifeOps — Data Model (Phase 1)

PostgreSQL 16. All tables have UUID PKs (`gen_random_uuid()`), `created_at`,
`updated_at` (`timestamptz`, UTC), and no soft deletes (judged unnecessary in v1; the
one place deletion exists — manual logs — is a simple hard delete by explicit user
action).

Cross-cutting columns of note:

- `users.timezone` — IANA zone, seeded as the reporting timezone (UTC+7).
- `ingestion_runs.run_metadata` / `alerts.context` / `source_connections.config` —
  JSONB; flexible payloads, typed accessors added when producers exist.
- All FKs declare their `ondelete` behavior explicitly (CASCADE for user-owned data,
  SET NULL for pure audit links like `raw_source_objects.user_id`).

## Tables (migration 0001 + 0002)

| Table | Purpose | Keys / constraints |
|---|---|---|
| `users` | Single seeded user (v1); multi-ready via user_id FKs | `email` unique |
| `source_connections` | Per-source OAuth/config + incremental cursor | unique(user, source), status/mode CHECK |
| `ingestion_runs` | One extraction run: windows, counters, status | status/run_type CHECK, counters non-negative, window_valid, ix (source, started_at DESC) |
| `ingestion_errors` | Structured error rows per run (stage, detail JSONB) | FK run ON DELETE CASCADE |
| `raw_source_objects` | Bronze idempotency ledger: object_key, sha256, bytes, window, schema_version, ingested_at | unique(source, dataset, sha256, window_start); object_key unique |
| `manual_daily_logs` | One row per (user, local day): sleep, mood, study, coding, workout, soccer, notes, tags | unique(user, log_date); range CHECKs (mood 1..5, hours 0..24, minutes 0..1440) |
| `expenses` | Transactions (VND/ISO3 currency) | amount > 0, currency length 3, ix(user, expense_date) |
| `alerts` | Anomaly detections: rule, severity, lifecycle | severity/status CHECK |
| `notification_channels` | Pluggable channel config; secrets stay in env | type CHECK |
| `report_snapshots` | Weekly/monthly report payloads (JSONB) | unique(user, type, period_start) |
| `pipeline_config` | Config table for weights (Life Balance) & thresholds | PK key |

## Bronze dataset paths (issue in docs, stored as files)

| Layer prefix | Datasets |
|---|---|
| `bronze/manual_logs/` | `daily_logs/` |
| `bronze/github/` | `commits/` |
| `bronze/calendar/` | `events/` |
| `bronze/spotify/` | `recently_played/` |
| `bronze/weather/` | `daily/` |
| `bronze/expenses/` | (Phase 11) |

## Planned (Phases 4/5): Silver Parquet & Gold star schema

- Silver: typed Parquet datasets per source with `_lifeops_silver_version`,
  raw-object key provenance, dedupe keys.
- Gold: `dim_date, dim_source, dim_activity_type, dim_project, dim_artist, dim_track,
  dim_expense_category`, facts (`fct_coding_activity, fct_calendar_events,
  fct_music_plays, fct_daily_habits, fct_expenses, fct_workouts,
  fct_daily_activity_summary`) and aggregates (`agg_weekly_life_report,
  agg_habit_consistency, agg_spending_by_category`).
