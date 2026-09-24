import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import psutil
import pytest

from sherlock.capabilities.processes.collector import ProcessCollector
from sherlock.capabilities.processes.models import (
    ProcessMetric,
    ProcessSnapshot,
)
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.process_repository import ProcessRepository
from sherlock.storage.sqlite.schema import MIGRATIONS, SCHEMA_VERSION


@pytest.fixture
def snapshot() -> ProcessSnapshot:
    timestamp = datetime(
        2026,
        9,
        24,
        17,
        0,
        tzinfo=timezone(timedelta(hours=3)),
    )

    metric = ProcessMetric(
        observed_at=timestamp,
        pid=123,
        create_time=1_700_000_000.25,
        name="example.exe",
        status="running",
        memory_rss=50 * 1024 * 1024,
        cpu_seconds=12.5,
    )

    return ProcessSnapshot(
        started_at=timestamp,
        finished_at=timestamp,
        processes=(metric,),
        skipped_count=0,
    )


def test_repository_preserves_process_identity_and_utc(
    tmp_path,
    snapshot,
):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()

    repository = ProcessRepository(database)

    first_id = repository.save(snapshot)

    second_metric = replace(
        snapshot.processes[0],
        create_time=1_700_001_000.5,
        name="another.exe",
        memory_rss=None,
        cpu_seconds=None,
    )
    second_snapshot = replace(
        snapshot,
        processes=(second_metric,),
    )

    second_id = repository.save(second_snapshot)

    rows = repository.history(pid=123)

    assert first_id != second_id
    assert len(rows) == 2

    assert rows[0]["snapshot_id"] == second_id
    assert rows[0]["create_time"] == 1_700_001_000.5
    assert rows[0]["name"] == "another.exe"
    assert rows[0]["memory_rss"] is None
    assert rows[0]["cpu_seconds"] is None

    assert rows[1]["snapshot_id"] == first_id
    assert rows[1]["create_time"] == 1_700_000_000.25
    assert rows[1]["memory_rss"] == 50 * 1024 * 1024
    assert rows[1]["cpu_seconds"] == 12.5
    assert (
        rows[1]["observed_at"]
        == "2026-09-24T14:00:00.000000+00:00"
    )

    assert len(repository.history(pid=123, limit=1)) == 1
    assert repository.history(pid=999) == []


def test_failed_snapshot_is_rolled_back(tmp_path, snapshot):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()

    repository = ProcessRepository(database)
    saved_id = repository.save(snapshot)

    # Two records with the same PID in one snapshot are invalid.
    duplicate_snapshot = replace(
        snapshot,
        processes=(
            snapshot.processes[0],
            snapshot.processes[0],
        ),
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(duplicate_snapshot)

    with database.connection() as connection:
        snapshots_count = connection.execute(
            "SELECT COUNT(*) FROM process_snapshots"
        ).fetchone()[0]

        metrics_count = connection.execute(
            "SELECT COUNT(*) FROM process_metrics"
        ).fetchone()[0]

    assert snapshots_count == 1
    assert metrics_count == 1
    assert repository.history(123)[0]["snapshot_id"] == saved_id


def test_empty_snapshot_is_saved(tmp_path, snapshot):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()

    repository = ProcessRepository(database)

    empty_snapshot = replace(
        snapshot,
        processes=(),
        skipped_count=3,
    )
    snapshot_id = repository.save(empty_snapshot)

    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT skipped_count
            FROM process_snapshots
            WHERE id = ?
            """,
            (snapshot_id,),
        ).fetchone()

        metrics_count = connection.execute(
            "SELECT COUNT(*) FROM process_metrics"
        ).fetchone()[0]

    assert row["skipped_count"] == 3
    assert metrics_count == 0


@pytest.mark.parametrize(
    "mode",
    [
        "available",
        "partial",
        "gone",
        "denied",
        "reused",
    ],
)
def test_collector_handles_process_states(monkeypatch, mode):
    class FakeProcess:
        def __init__(self, pid):
            assert pid == 123
            self.checks = 0

        def create_time(self):
            if mode == "denied":
                raise psutil.AccessDenied(pid=123)

            return 1_700_000_000.25

        def is_running(self):
            self.checks += 1

            return not (
                mode == "reused" and self.checks == 2
            )

        def as_dict(self, attrs, ad_value):
            assert attrs == [
                "name",
                "status",
                "memory_info",
                "cpu_times",
            ]
            assert ad_value is None

            if mode == "gone":
                raise psutil.NoSuchProcess(pid=123)

            if mode == "partial":
                return {
                    "name": None,
                    "status": "running",
                    "memory_info": None,
                    "cpu_times": None,
                }

            return {
                "name": "example.exe",
                "status": "running",
                "memory_info": SimpleNamespace(rss=4096),
                "cpu_times": SimpleNamespace(
                    user=2.0,
                    system=0.5,
                    children_user=100.0,
                    children_system=100.0,
                ),
            }

    monkeypatch.setattr(psutil, "pids", lambda: [123])
    monkeypatch.setattr(psutil, "Process", FakeProcess)

    before = datetime.now(timezone.utc)
    result = ProcessCollector().collect()
    after = datetime.now(timezone.utc)

    assert before <= result.started_at <= result.finished_at <= after

    if mode in {"gone", "denied", "reused"}:
        assert result.processes == ()
        assert result.skipped_count == 1
        return

    assert result.skipped_count == 0
    assert len(result.processes) == 1

    metric = result.processes[0]

    assert metric.pid == 123
    assert metric.create_time == 1_700_000_000.25
    assert result.started_at <= metric.observed_at <= result.finished_at

    if mode == "partial":
        assert metric.name is None
        assert metric.memory_rss is None
        assert metric.cpu_seconds is None
    else:
        assert metric.name == "example.exe"
        assert metric.memory_rss == 4096

        assert metric.cpu_seconds == 2.5


def test_migration_from_version_two_preserves_telemetry(tmp_path):
    path = tmp_path / "sherlock.db"

    connection = sqlite3.connect(path)

    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE schema_info (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    version INTEGER NOT NULL
                )
                """
            )

            for version in (1, 2):
                for statement in MIGRATIONS[version]:
                    connection.execute(statement)

            connection.execute(
                "INSERT INTO schema_info (id, version) VALUES (1, 2)"
            )

            connection.execute(
                """
                INSERT INTO system_metrics (
                    timestamp,
                    cpu_percent,
                    memory_percent,
                    memory_used,
                    memory_available,
                    swap_percent
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-09-24T14:00:00.000000+00:00",
                    10.0,
                    50.0,
                    1000,
                    1000,
                    0.0,
                ),
            )
    finally:
        connection.close()

    database = Database(path)

    database.initialize()
    database.initialize()

    assert database.get_schema_version() == SCHEMA_VERSION

    with database.connection() as connection:
        metric = connection.execute(
            "SELECT cpu_percent FROM system_metrics"
        ).fetchone()

        snapshots_count = connection.execute(
            "SELECT COUNT(*) FROM process_snapshots"
        ).fetchone()[0]

        processes_count = connection.execute(
            "SELECT COUNT(*) FROM process_metrics"
        ).fetchone()[0]

    assert metric["cpu_percent"] == 10.0
    assert snapshots_count == 0
    assert processes_count == 0


def test_process_timestamp_requires_timezone(snapshot):
    with pytest.raises(ValueError, match="timezone"):
        replace(
            snapshot.processes[0],
            observed_at=datetime(2026, 9, 24, 17, 0),
        )
