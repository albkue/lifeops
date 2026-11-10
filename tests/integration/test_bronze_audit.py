"""Bronze auditor (missing/corrupt/ok) + ledger catalog + runs window filters."""

import pytest

pytestmark = pytest.mark.integration

from datetime import UTC, datetime, timedelta  # noqa: E402

from lifeops_core.models.enums import RunType  # noqa: E402
from lifeops_core.repositories.ingestion_runs import IngestionRunRepository  # noqa: E402
from lifeops_core.repositories.raw_source_objects import (  # noqa: E402
    RawSourceObjectRepository,
)
from lifeops_core.storage.audit import BronzeAuditor  # noqa: E402
from lifeops_core.storage.bronze import BronzeStorage  # noqa: E402
from lifeops_core.storage.object_store import MinioObjectStore  # noqa: E402

DAY = datetime(2026, 11, 5, tzinfo=UTC)
NEXT_DAY = DAY + timedelta(days=1)


def _bronze(settings, session_factory) -> tuple[BronzeStorage, MinioObjectStore]:
    store = MinioObjectStore.from_settings(settings)
    return BronzeStorage(store, session_factory), store


def _write(
    bronze: BronzeStorage,
    *,
    source: str = "github",
    dataset: str = "commits",
    payload: dict | None = None,
    window: tuple[datetime, datetime] = (DAY, NEXT_DAY),
):
    """Write one bronze object, return (result, object_key)."""
    payload = payload or {"items": [{"sha": "aa" * 20}], "fetch_date": "2026-11-05"}
    result = bronze.write(
        source_name=source,
        dataset=dataset,
        payload=payload,
        user_id=None,
        window_start=window[0],
        window_end=window[1],
    )
    return result, result.object_key


def _seed_ledger_rows(session_factory, count: int = 5, source="github", dataset="tags"):
    """Create catalog rows directly (no object store needed for paging tests)."""
    from datetime import datetime as dt

    with session_factory() as session:
        repo = RawSourceObjectRepository(session)
        for i in range(count):
            repo.insert(
                source_name=source,
                dataset=dataset,
                object_key=f"bronze/{source}/{dataset}/test/{i}.json",
                payload_sha256=f"{i:064d}",
                payload_bytes=100 + i,
                ingested_at=dt(2026, 11, 5, 12, i, tzinfo=UTC),
                extraction_window_start=DAY + timedelta(days=i),
                extraction_window_end=DAY + timedelta(days=i + 1),
            )
        session.commit()


def _auditor(store, session_factory) -> BronzeAuditor:
    return BronzeAuditor(store, session_factory)


def _test_settings():  # placeholder; replaced below via fixture-parameterized tests
    import os

    from lifeops_core.config import Settings

    return Settings(
        database_url=os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://test/test"),
        minio_endpoint=os.environ.get("TEST_MINIO_ENDPOINT", "unreachable:9000"),
        minio_bucket="lifeops-test",
        timezone_name="Asia/Ho_Chi_Minh",
    )


class TestBronzeAuditor:
    def test_all_ok_after_clean_write(self, settings, ensure_bucket, session_factory):
        if not ensure_bucket:
            pytest.skip("no object store available")
        bronze, store = _bronze(settings, session_factory)
        _write(bronze)

        report = _auditor(store, session_factory).audit("github", dataset="commits")
        assert report.ledger_rows == 1
        assert report.ok == 1
        assert report.missing == 0
        assert report.problems == []

    def test_detects_missing_object(self, settings, ensure_bucket, session_factory):
        if not ensure_bucket:
            pytest.skip("no object store available")
        bronze, store = _bronze(settings, session_factory)
        _, key = _write(bronze)
        store.remove_object(key)

        report = _auditor(store, session_factory).audit("github", dataset="commits")
        assert report.missing == 1 and report.ok == 0
        assert report.problems[0].problem == "missing"
        assert report.problems[0].object_key == key

    def test_detects_corrupt_object(self, settings, ensure_bucket, session_factory):
        if not ensure_bucket:
            pytest.skip("no object store available")
        bronze, store = _bronze(settings, session_factory)
        _, key = _write(bronze)
        store.put_bytes(key, b'{"payload": {"items": ["TAMPERED"]}}')

        report = _auditor(store, session_factory).audit("github", dataset="commits")
        assert report.corrupt == 1
        assert report.problems[0].problem == "corrupt"
        assert "digest mismatch" in (report.problems[0].detail or "")

    def test_window_filter_limits_audit_scope(self, settings, ensure_bucket, session_factory):
        if not ensure_bucket:
            pytest.skip("no object store available")
        bronze, store = _bronze(settings, session_factory)
        _write(bronze, source="weather", dataset="daily", payload={"daily": []})
        other_day = datetime(2026, 11, 1, tzinfo=UTC)
        bronze.write(
            source_name="weather",
            dataset="daily",
            payload={"daily": [2]},
            window_start=other_day,
            window_end=other_day + timedelta(days=1),
        )

        report = _auditor(store, session_factory).audit(
            "weather", window_start=DAY, window_end=NEXT_DAY
        )
        assert report.ledger_rows == 1

    def test_unknown_source_yields_empty_report(self, ensure_bucket, session_factory):
        if not ensure_bucket:
            pytest.skip("no object store available")
        store = MinioObjectStore.from_settings(_test_settings())
        report = _auditor(store, session_factory).audit("nonexistent-source")
        assert report.ledger_rows == 0 and report.problems == []


class TestLedgerCatalog:
    def test_list_page_filters(self, session_factory):
        _seed_ledger_rows(session_factory, count=5, source="calendar", dataset="events")
        with session_factory() as session:
            repo = RawSourceObjectRepository(session)
            items, total = repo.list_page(source_name="calendar")
            assert total == 5 and all(i.dataset == "events" for i in items)

            # overlap filter keeps the row covering [DAY, NEXT_DAY)
            items, total = repo.list_page(
                source_name="calendar", window_start=DAY, window_end=NEXT_DAY
            )
            assert total == 1 and items[0].extraction_window_start == DAY

    def test_list_page_pagination(self, session_factory):
        _seed_ledger_rows(session_factory, count=5)
        with session_factory() as session:
            repo = RawSourceObjectRepository(session)
            items, total = repo.list_page(source_name="github", dataset="tags", limit=2)
            assert total == 5 and len(items) == 2
            items, total = repo.list_page(source_name="github", dataset="tags", limit=5, offset=4)
            assert total == 5 and len(items) == 1


class TestRunWindowFilters:
    def test_list_runs_window_overlap(self, session_factory, user_id):
        with session_factory() as session:
            repo = IngestionRunRepository(session)
            repo.create(
                user_id=user_id,
                source_name="github",
                run_type=RunType.MANUAL,
                window_start=DAY,
                window_end=NEXT_DAY,
            )
            repo.create(
                user_id=user_id,
                source_name="github",
                run_type=RunType.MANUAL,
                window_start=datetime(2026, 11, 20, tzinfo=UTC),
                window_end=datetime(2026, 11, 21, tzinfo=UTC),
            )
            repo.create(
                user_id=user_id,
                source_name="github",
                run_type=RunType.MANUAL,
                window_start=None,
                window_end=None,
            )
            session.commit()

            _, total = repo.list_runs(source_name="github", window_from=DAY, window_to=NEXT_DAY)
            # only the overlapping-window run; windowless runs never match
            assert total == 1
