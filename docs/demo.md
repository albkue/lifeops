# LifeOps — Local demo & operations guide

Goal of this doc: reproduce the full Phase-1 demo from a clean machine, including the
2026 MinIO→SeaweedFS note.

## 0. Prerequisites

- Docker Desktop running
- Python 3.11+ (for the local venv tooling; everything heavy runs in Docker)
- GNU make (Git Bash/WSL on Windows)

## 1. Configure

```bash
cp .env.example .env
# If host port 5432/9000/8000/8001 collide (e.g. another Postgres), override:
#   POSTGRES_PORT=5433  etc.
```

## 2. Start the stack

```bash
docker compose up -d
docker compose ps
# expected: postgres (healthy), minio->SeaweedFS (healthy),
# storage-init Exited(0), migrate Exited(0),
# ingestion-api Up (:8000), insights-api Up (:8001)
```

Health: `curl http://localhost:8000/api/v1/health` → `{"status":"ok",...}`.

> **2026 MinIO note:** the `minio` service name lives on, but v1 runs the
> **SeaweedFS** image (S3-compatible) because MinIO's official images are
> login/license-gated on all registries (verified 2026-11-10). To restore real MinIO:
> `docker login quay.io`, then set `MINIO_IMAGE=quay.io/minio/minio:latest` in `.env`.
> The Bronze client (`lifeops_core.storage`) is plain S3 and unaffected.

## 3. Demo data (deterministic, no external API)

```bash
make seed-demo         # 90 days: 90 logs, 107 expenses, 450 runs, ~443 bronze objects
# equivalent: docker compose run --rm -e MINIO_BUCKET=lifeops tests python scripts/seed_demo_data.py --days 90
```

What you can verify immediately:

```bash
curl -s http://localhost:8000/api/v1/metrics
# counts: manual_daily_logs=90, expenses=107, ingestion_runs=450,
# raw_source_objects≈443 (2% of scheduled runs fail on purpose for the alerts demo)

curl -s 'http://localhost:8000/api/v1/logs/daily?start_date=2026-11-01&end_date=2026-11-10'
```

Bucket walk-through (optional):

```bash
python - <<'PY'
from minio import Minio
c = Minio('localhost:9000', access_key='lifeops', secret_key='lifeops-secret', secure=False)
for o in list(c.list_objects('lifeops', recursive=True))[:5]:
    print(o.object_name)
PY
# → bronze/github/commits/extr_date=2026-11-08/ingested_at=...Z/abcd1234-....json
```

Bronze object layout (`{"payload": ..., "_lifeops_meta": {...}}`) is documented in
`docs/architecture.md`.

## 4. Development loop

```bash
make test      # 42 tests inside Docker (postgres + object store from compose)
make check     # ruff + mypy (same gates as CI)
make logs      # tail everything
```

Useful dev helpers (run from the repo root locally):
- `scripts/row_counts.py`, `scripts/inspect_db.py` — quick DB sanity
- `scripts/wipe_tables.py` — reset DB rows before re-seeding a demo

## 5. Re-seeding cleanly

```bash
docker compose run --rm tests python scripts/wipe_tables.py
make seed-demo
```
(Objects in the bucket persist; the ledger re-dedupes on identical payloads, so
re-seeding after a DB wipe writes only new events. To fully refresh the bucket, delete
it first — see §3 script pattern with `remove_bucket`.)

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `migrate` Exited(1) `Can't locate revision` | image built before a new migration file | `docker compose build migrate ingestion-api insights-api` then `docker compose up -d` |
| port 5432/9000/8000/8001 already allocated | another local stack | change `POSTGRES_PORT`, `MINIO_CONSOLE_PORT`, `INGESTION_API_PORT`, `INSIGHTS_API_PORT` in `.env` |
| MinIO image pull denied | MinIO registry gating (2026) | use SeaweedFS default or `docker login quay.io` |
| Bronze `deduplicated: true` right after wipe | payload-level SHA ledger Did not have rows | seed again, or wipe ledger table too |
