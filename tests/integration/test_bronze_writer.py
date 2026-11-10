"""BronzeStorage idempotency contract (integration: real MinIO)."""

from datetime import UTC, date, datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

from lifeops_core.storage.bronze import BronzeStorage  # noqa: E402
from lifeops_core.storage.object_store import MinioObjectStore  # noqa: E402


@pytest.fixture()
def bronze_storage(settings, ensure_bucket, session_factory):
    if not ensure_bucket:
        pytest.skip("MinIO not available")
    store = MinioObjectStore.from_settings(settings)
    return BronzeStorage(store, session_factory)


def _window(day: date):
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def test_first_write_stores_object(bronze_storage):
    ws, we = _window(date(2026, 11, 2))
    result = bronze_storage.write(
        source_name="github",
        dataset="commits",
        payload={"items": [{"sha": "abc" * 13 + "a"}], "fetch_date": "2026-11-02"},
        user_id=None,
        window_start=ws,
        window_end=we,
    )
    assert result.deduplicated is False
    assert result.object_key.startswith("bronze/github/commits/extr_date=2026-11-02/")
    assert len(result.sha256) == 64


def test_same_payload_same_window_is_deduplicated(bronze_storage):
    payload = {"items": [{"sha": "def" * 13 + "9"}], "fetch_date": "2026-11-03"}
    ws, we = _window(date(2026, 11, 3))
    first = bronze_storage.write(
        source_name="github", dataset="commits", payload=payload, window_start=ws, window_end=we
    )
    second = bronze_storage.write(
        source_name="github", dataset="commits", payload=payload, window_start=ws, window_end=we
    )
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert second.sha256 == first.sha256


def test_same_payload_different_window_is_stored(bronze_storage):
    payload = {"items": [{"sha": "fff" * 13 + "1"}], "fetch_date": "2026-11-04"}
    w1 = _window(date(2026, 11, 4))
    w2 = _window(date(2026, 11, 5))
    first = bronze_storage.write(
        source_name="weather",
        dataset="daily",
        payload=payload,
        window_start=w1[0],
        window_end=w1[1],
    )
    second = bronze_storage.write(
        source_name="weather",
        dataset="daily",
        payload=payload,
        window_start=w2[0],
        window_end=w2[1],
    )
    assert first.deduplicated is False
    assert second.deduplicated is False


def test_stored_object_layout_has_envelope(bronze_storage, settings):
    import json

    ws, we = _window(date(2026, 11, 6))
    result = bronze_storage.write(
        source_name="calendar",
        dataset="events",
        payload={"kind": "calendar_events", "items": []},
        window_start=ws,
        window_end=we,
    )
    client_store = MinioObjectStore.from_settings(settings)
    data = client_store._client.get_object(settings.minio_bucket, result.object_key)
    body = data.read()
    doc = json.loads(body)
    assert "payload" in doc
    assert "_lifeops_meta" in doc
    meta = doc["_lifeops_meta"]
    assert meta["source"] == "calendar"
    assert meta["dataset"] == "events"
    assert meta["schema_version"] == "v1"
    assert meta["extraction_window_start"].startswith("2026-11-06")
    data.close()
    data.release_conn()
