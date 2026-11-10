# LifeOps — REST API (current as of Phase 1)

Both services expose OpenAPI: `http://localhost:8000/docs`, `http://localhost:8001/docs`.

Conventions:
- Errors: `{"error", "message", "details", "service"}` with proper HTTP codes
  (400/404/409/422/503/501 as applicable).
- Timestamps ISO-8601 UTC. Day fields are local dates (reporting timezone UTC+7).
- Pagination: `limit` (1..200) + `offset` with `total`.

## ingestion-api (:8000)

### Manual daily log

| Method | Path | Notes |
|---|---|---|
| `POST /api/v1/logs/daily` | upsert by (user, log_date) | **201** created / **200** merged; validates fields, far-future dates rejected (max tomorrow) |
| `GET /api/v1/logs/daily` | range list (`start_date`, `end_date`, `limit`, `offset`) | **200** page |
| `GET /api/v1/logs/daily/by-date/{date}` | single day | 404 JSON when absent |
| `PATCH /api/v1/logs/daily/{id}` | explicit field override | fields omitted = no-op |
| `DELETE /api/v1/logs/daily/{id}` | delete | **204** |

Fields: `sleep_hours 0..24`, `mood_score 1..5`, `study_hours 0..24`,
`coding_hours 0..24`, `workout_minutes 0..1440`, `soccer_minutes 0..1440`,
`notes` (max 2000 chars), `tags` (≤10, trimmed/lowercased/deduped).
All optional except `log_date`.

`POST` merges fields only when provided (a mobile quick-entry never needs to resend
the whole day).

### Ingestion

| Method | Path | Phase-1 behavior |
|---|---|---|
| `GET /api/v1/ingestion/sources` | lists known sources + adapter availability | `adapter_available=false` until Phase 6/7/11 |
| `POST /api/v1/ingestion/{source}/run` | trigger incremental run | 202 with run payload; **501** (Source Adapter Not Available) until adapters land |
| `POST /api/v1/ingestion/{source}/backfill` | window re-run (idempotent) | body requires `window_start`+`window_end`; max 120 days |
| `GET /api/v1/ingestion/runs` | list runs (filter: `source_name`, `status`, `run_type`) | 200 page |

### Observability

| Method | Path | Notes |
|---|---|---|
| `GET /api/v1/health` | DB critical (503 when down); object store degrades only (200) | components listed |
| `GET /api/v1/metrics` | counts + last run per source (freshness panel input) | — |

## insights-api (:8001)

| Method | Path | Notes |
|---|---|---|
| `GET /api/v1/health` | same readiness contract | — |
| `/api/v1/insights/*`, `/api/v1/reports/*` | Phase 8 — routing exists in the Gold mart contract (README features) | not implemented yet |

## Example flow (works today)

```bash
# 1. upsert today's log (mobile-quick)
curl -s -X POST http://localhost:8000/api/v1/logs/daily \
  -H 'Content-Type: application/json' \
  -d '{"log_date":"2026-11-10","sleep_hours":7.2,"mood_score":4,"coding_hours":3.5,"tags":["deep-work"]}'
# → 201 {"record":{...},"created":true,"bronze":{"object_key":"bronze/manual_logs/daily_logs/...","sha256":"...","deduplicated":false}}

# 2. re-submit (idempotent)
# → 200 {"created":false,...,"bronze":{"deduplicated":true,...}}   ← sha ledger hit

# 3. read range
curl -s 'http://localhost:8000/api/v1/logs/daily?start_date=2026-11-01&end_date=2026-11-30'

# 4. pipeline health for dashboards
curl -s http://localhost:8000/api/v1/metrics
```
