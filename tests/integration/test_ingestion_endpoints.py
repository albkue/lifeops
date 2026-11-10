"""Ingestion service HTTP contract in Phase 1 (adapters come Phase 6+)."""

import pytest

pytestmark = pytest.mark.integration


def test_sources_lists_known_sources(client):
    response = client.get("/api/v1/ingestion/sources")
    assert response.status_code == 200
    names = {s["name"] for s in response.json()["sources"]}
    assert {"github", "calendar", "spotify", "weather", "expenses"} <= names


def test_run_known_source_without_adapter_returns_501(client):
    response = client.post("/api/v1/ingestion/github/run", json={})
    assert response.status_code == 501
    body = response.json()
    assert body["error"] == "Source Adapter Not Available"


def test_run_unknown_source_returns_422(client):
    response = client.post("/api/v1/ingestion/not-a-source/run", json={})
    assert response.status_code == 422
    assert "known_sources" in response.json()["details"]


def test_backfill_requires_window(client):
    response = client.post("/api/v1/ingestion/github/backfill", json={})
    assert response.status_code == 422
    assert "window_start" in response.json()["message"]


def test_backfill_invalid_window_order(client):
    response = client.post(
        "/api/v1/ingestion/github/backfill",
        json={"window_start": "2026-11-10", "window_end": "2026-11-01"},
    )
    assert response.status_code == 422


def test_runs_listing_empty_page(client):
    response = client.get("/api/v1/ingestion/runs")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_metrics_reports_counts(client, session_factory, user_id):
    # seed one run through the repo to make sure latest_runs surfaces it
    from lifeops_core.models.enums import RunType
    from lifeops_core.repositories.ingestion_runs import IngestionRunRepository

    with session_factory() as session:
        IngestionRunRepository(session).create(
            user_id=user_id, source_name="github", run_type=RunType.MANUAL
        )
        session.commit()

    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    body = response.json()
    counts = {c["key"]: c["value"] for c in body["counts"]}
    assert counts["ingestion_runs"] >= 1
    assert any(r["source_name"] == "github" for r in body["latest_runs"])
