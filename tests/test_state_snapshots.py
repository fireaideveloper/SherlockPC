import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from sherlock.capabilities.processes.models import (
    ProcessMetric,
    ProcessSnapshot,
)
from sherlock.capabilities.state.collector import StateCollector
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.schema import MIGRATIONS, SCHEMA_VERSION
from sherlock.storage.sqlite.state_repository import StateRepository


@pytest.fixture
def state() -> StateSnapshot:
    timestamp = datetime(
        2026,
        9,
        24,
        17,
        0,
        tzinfo=timezone(timedelta(hours=3)),
    )

    system = SystemMetric(
        timestamp=timestamp,
        cpu_percent=25.0,
        memory_percent=50.0,
        memory_used=4096,
        memory_available=4096,
        swap_percent=0.0,
        disk_read_bytes=None,
        disk_write_bytes=None,
        network_rx_bytes=None,
        network_tx_bytes=None,
    )

    process = ProcessMetric(
        observed_at=timestamp,
        pid=123,
        create_time=1_700_000_000.25,
        name="example.exe",
        status="running",
        memory_rss=2048,
        cpu_seconds=2.5,
    )

    processes = ProcessSnapshot(
        started_at=timestamp,
        finished_at=timestamp,
        processes=(process,),
        skipped_count=2,
    )

    return StateSnapshot(
        started_at=timestamp,
        finished_at=timestamp,
        system=system,
        processes=processes,
    )


def test_state_save_links_observations(tmp_path, state):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()

    repository = StateRepository(database)
    state_id = repository.save(state)

    rows = repository.recent()

    assert len(rows) == 1

    row = rows[0]

    assert row["id"] == state_id
    assert row["started_at"] == "2026-09-24T14:00:00.000000+00:00"
    assert row["finished_at"] == "2026-09-24T14:00:00.000000+00:00"
    assert row["cpu_percent"] == 25.0
    assert row["memory_percent"] == 50.0
    assert row["process_count"] == 1
    assert row["skipped_count"] == 2

    with database.connection() as connection:
        linked_process = connection.execute(
            """
            SELECT metric.pid, metric.create_time
            FROM state_snapshots AS state
            JOIN process_metrics AS metric
                ON metric.snapshot_id = state.process_snapshot_id
            WHERE state.id = ?
            """,
            (state_id,),
        ).fetchone()

    assert linked_process["pid"] == 123
    assert linked_process["create_time"] == 1_700_000_000.25


def test_state_save_rolls_back_all_parts(tmp_path, state):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()

    repository = StateRepository(database)

    # Keep one valid snapshot to verify that rollback preserves it.
    saved_id = repository.save(state)

    metric = state.processes.processes[0]

    invalid_processes = replace(
        state.processes,
        processes=(metric, metric),
    )

    invalid_state = replace(
        state,
        processes=invalid_processes,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(invalid_state)

    with database.connection() as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM system_metrics),
                (SELECT COUNT(*) FROM process_snapshots),
                (SELECT COUNT(*) FROM process_metrics),
                (SELECT COUNT(*) FROM state_snapshots)
            """
        ).fetchone()

    assert tuple(counts) == (1, 1, 1, 1)
    assert repository.recent()[0]["id"] == saved_id


def test_state_collector_coordinates_sources(state):
    calls = []

    def collect_system():
        calls.append("system")
        return state.system

    def collect_processes():
        calls.append("processes")
        return state.processes

    collector = StateCollector(
        telemetry_collector=SimpleNamespace(
            collect=collect_system,
        ),
        process_collector=SimpleNamespace(
            collect=collect_processes,
        ),
    )

    before = datetime.now(timezone.utc)
    result = collector.collect()
    after = datetime.now(timezone.utc)

    assert calls == ["system", "processes"]
    assert result.system is state.system
    assert result.processes is state.processes
    assert before <= result.started_at <= result.finished_at <= after


def test_recent_states_are_limited_and_newest_first(tmp_path, state):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()

    repository = StateRepository(database)

    first_id = repository.save(state)
    second_id = repository.save(state)

    rows = repository.recent(limit=1)

    assert first_id != second_id
    assert len(rows) == 1
    assert rows[0]["id"] == second_id

    with pytest.raises(ValueError):
        repository.recent(limit=0)


def test_migration_from_version_three_preserves_data(tmp_path):
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

            for version in (1, 2, 3):
                for statement in MIGRATIONS[version]:
                    connection.execute(statement)

            connection.execute(
                "INSERT INTO schema_info (id, version) VALUES (1, 3)"
            )

            connection.execute(
                """
                INSERT INTO process_snapshots (
                    started_at,
                    finished_at,
                    skipped_count
                )
                VALUES (?, ?, ?)
                """,
                (
                    "2026-09-24T14:00:00.000000+00:00",
                    "2026-09-24T14:00:01.000000+00:00",
                    2,
                ),
            )

            connection.execute(
                """
                INSERT INTO process_metrics (
                    snapshot_id,
                    observed_at,
                    pid,
                    create_time,
                    name,
                    status,
                    memory_rss,
                    cpu_seconds
                )
                VALUES (1, ?, 123, 1700000000.25, ?, ?, 2048, 2.5)
                """,
                (
                    "2026-09-24T14:00:00.500000+00:00",
                    "example.exe",
                    "running",
                ),
            )
    finally:
        connection.close()

    database = Database(path)

    database.initialize()
    database.initialize()

    assert database.get_schema_version() == SCHEMA_VERSION

    with database.connection() as connection:
        old_metric = connection.execute(
            "SELECT pid, name FROM process_metrics"
        ).fetchone()

        state_count = connection.execute(
            "SELECT COUNT(*) FROM state_snapshots"
        ).fetchone()[0]

    assert old_metric["pid"] == 123
    assert old_metric["name"] == "example.exe"

    # Old independent observations must not be grouped automatically.
    assert state_count == 0
