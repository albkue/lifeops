# LifeOps Makefile — thin wrappers around docker compose / local tooling.
# Windows note: use Docker Desktop + GNU make (Git Bash/WSL). Every target
# documents the equivalent raw command so you can always run it by hand.

.PHONY: help up down restart logs ps migrate seed-demo generate-sample test test-unit api-insights openapi lint fmt type-check check dbt-run dbt-test

help:
	@echo "LifeOps targets:"
	@echo "  up                docker compose up -d --build (postgres, minio, ingestion-api, insights-api)"
	@echo "  down              docker compose down"
	@echo "  logs              docker compose logs -f"
	@echo "  migrate           docker compose run --rm migrate   (alembic upgrade head)"
	@echo "  seed-demo         seed demo user + sample data into the full stack"
	@echo "  generate-sample   run the sample data generator (host python or container)"
	@echo "  test              run pytest inside the compose test container"
	@echo "  test-unit         tag-filtered local pytest"
	@echo "  api-insights      local notes for API usage"
	@echo "  lint / fmt / type-check / check"
	@echo "  dbt-run / dbt-test (activated in Phase 5)"

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose down
	docker compose up -d --build

logs:
	docker compose logs -f --tail=50

ps:
	docker compose ps

migrate:
	docker compose run --rm migrate

seed-demo:
	docker compose run --rm -e MINIO_BUCKET=lifeops tests python scripts/seed_demo_data.py --days 90

generate-sample:
	docker compose run --rm -e MINIO_BUCKET=lifeops tests python scripts/generate_sample_data.py --days 90

# Runs the full suite inside Docker (postgres + minio cometh from compose).
test:
	docker compose run --rm tests

# Local venv variant (requires TEST_DATABASE_URL / TEST_MINIO_ENDPOINT or testcontainers).
test-unit:
	.venv/bin/python -m pytest tests/unit -q

lint:
	ruff check .

fmt:
	ruff check --fix . && ruff format .

type-check:
	mypy .

check: lint type-check

dbt-run:
	@echo "[lifeops] dbt models land in Phase 5 — this target will run 'dbt build' in dbt/ then. See docs/roadmap."

dbt-test:
	@echo "[lifeops] dbt tests land in Phase 5 together with dbt-run."
