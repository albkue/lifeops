"""Bronze wire-format unit tests (serialization, hashing, key layout)."""

import hashlib
import json
from datetime import UTC, date, datetime

import pytest

pytestmark = pytest.mark.unit

from lifeops_core.storage.bronze import build_bronze_key, serialize_payload, sha256_hex  # noqa: E402


def test_layout_is_payload_plus_meta():
    raw = serialize_payload({"a": 1}, {"ingested_at": "2026-01-01", "source": "github"})
    doc = json.loads(raw)
    assert "payload" in doc
    assert "meta" not in doc
    assert doc["payload"]["a"] == 1


def test_envelope_never_mutates_payload():
    raw = serialize_payload({"items": [1, 2]}, {})
    body = json.loads(raw)
    assert body["payload"]["items"] == [1, 2]


def test_sha256_matches_stdlib():
    raw = b"anything"
    assert sha256_hex(raw) == hashlib.sha256(raw).hexdigest()


def test_bronze_key_layout_is_hive_partitioned():
    ingested = datetime(2026, 11, 9, 2, 30, tzinfo=UTC)
    key = build_bronze_key("github", "commits", date(2026, 11, 8), ingested, "abcd1234")
    assert key.startswith("bronze/github/commits/")
    assert "extr_date=2026-11-08/" in key
    assert "ingested_at=20261109T023000Z/" in key
    assert "abcd1234-" in key
    assert key.endswith(".json")


def test_bronze_key_window_optional():
    ingested = datetime(2026, 11, 9, 2, 30, tzinfo=UTC)
    key = build_bronze_key("weather", "daily", None, ingested, "beef0000")
    assert "extr_date=2026-11-09/" in key
