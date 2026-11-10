"""Health + readiness contract (integration: real DB, real MinIO optional)."""

import pytest

pytestmark = pytest.mark.integration


def test_health_endpoint_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ingestion-api"
    components = {component["name"]: component["status"] for component in body["components"]}
    assert components["database"] == "up"
