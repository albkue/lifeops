"""verify_bronze_object unit tests (canonical digest identity rules)."""

import pytest

pytestmark = pytest.mark.unit

from lifeops_core.storage.audit import (  # noqa: E402
    PayloadVerificationError,
    verify_bronze_object,
)
from lifeops_core.storage.bronze import serialize_payload, sha256_hex  # noqa: E402


def _stored_bytes(payload: dict, envelope: dict | None = None) -> bytes:
    return serialize_payload(payload, envelope or {"ingested_at": "2026-11-10T00:00:00+0000"})


class TestVerifyBronzeObject:
    def test_passes_when_digest_matches_ledger_rule(self):
        payload = {"items": [1, 2, 3], "fetch_date": "2026-11-02"}
        ledger_sha = sha256_hex(serialize_payload(payload))
        # must not raise
        verify_bronze_object(_stored_bytes(payload), ledger_sha)

    def test_detects_payload_tampering(self):
        payload = {"items": [1]}
        ledger_sha = sha256_hex(serialize_payload(payload))
        tampered = dict(payload, items=[2])
        with pytest.raises(PayloadVerificationError) as excinfo:
            verify_bronze_object(_stored_bytes(tampered), ledger_sha)
        assert excinfo.value.actual_sha256 is not None

    def test_detects_missing_payload_section(self):
        raw = b'{"_lifeops_meta":{}}'
        with pytest.raises(PayloadVerificationError):
            verify_bronze_object(raw, "0" * 64)

    def test_detects_non_json(self):
        raw = b"not-json{"
        with pytest.raises(PayloadVerificationError):
            verify_bronze_object(raw, "0" * 64)

    def test_envelope_changes_do_not_break_identity(self):
        """Core invariant: different ingestion timestamps hash the same."""
        payload = {"ok": True}
        ledger_sha = sha256_hex(serialize_payload(payload))
        b1 = serialize_payload(payload, {"ingested_at": "2026-11-09T00:00:00+0000"})
        b2 = serialize_payload(payload, {"ingested_at": "2026-11-10T12:34:56+0000"})
        assert b1 != b2  # bytes differ...
        # ...but identity verification passes for both
        verify_bronze_object(b1, ledger_sha)
        verify_bronze_object(b2, ledger_sha)
