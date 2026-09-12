from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from sherlock.capabilities.telemetry import collector as collector_module
from sherlock.capabilities.telemetry.collector import TelemetryCollector
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.telemetry_repository import (
    TelemetryRepository,
)


@pytest.fixture
def metric():
    return SystemMetric(
        timestamp=datetime(
            2026, 9, 12, 17, 0,
            tzinfo=timezone(timedelta(hours=3)),
        ),
        cpu_percent=25.0,
        memory_percent=50.0,
        memory_used=8_000,
        memory_available=8_000,
        swap_percent=2.0,
        disk_read_bytes=1_000,
        disk_write_bytes=2_000,
        network_rx_bytes=3_000,
        network_tx_bytes=4_000,
    )


def test_repository_saves_metrics_in_utc(tmp_path, metric):
    database = Database(tmp_path / "test.db")
    database.initialize()
    repository = TelemetryRepository(database)

    first_id = repository.save(metric)
    second_id = repository.save(metric)

    database.initialize()

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT * FROM system_metrics ORDER BY id"
        ).fetchall()

    assert first_id != second_id
    assert len(rows) == 2

    row = rows[0]

    assert row["timestamp"] == "2026-09-12T14:00:00.000000+00:00"
    assert row["cpu_percent"] == metric.cpu_percent
    assert row["memory_percent"] == metric.memory_percent
    assert row["memory_used"] == metric.memory_used
    assert row["memory_available"] == metric.memory_available
    assert row["swap_percent"] == metric.swap_percent
    assert row["disk_read_bytes"] == metric.disk_read_bytes
    assert row["disk_write_bytes"] == metric.disk_write_bytes
    assert row["network_rx_bytes"] == metric.network_rx_bytes
    assert row["network_tx_bytes"] == metric.network_tx_bytes


def test_missing_counters_are_saved_as_null(tmp_path, metric):
    database = Database(tmp_path / "test.db")
    database.initialize()
    repository = TelemetryRepository(database)

    missing = replace(
        metric,
        disk_read_bytes=None,
        disk_write_bytes=None,
        network_rx_bytes=None,
        network_tx_bytes=None,
    )

    metric_id = repository.save(missing)

    with database.connection() as connection:
        row = connection.execute(
            "SELECT * FROM system_metrics WHERE id = ?",
            (metric_id,),
        ).fetchone()

    assert row["disk_read_bytes"] is None
    assert row["disk_write_bytes"] is None
    assert row["network_rx_bytes"] is None
    assert row["network_tx_bytes"] is None


def test_timestamp_requires_timezone(metric):
    with pytest.raises(ValueError, match="timezone"):
        replace(metric, timestamp=datetime(2026, 9, 12))


@pytest.mark.parametrize(
    "io_mode",
    ["available", "missing", "error"],
)
def test_collector(monkeypatch, io_mode):
    def fake_cpu_percent(interval):
        assert interval == 1.0
        return 25.0

    def fake_disk():
        if io_mode == "error":
            raise OSError("Disk counters unavailable")

        if io_mode == "missing":
            return None

        return SimpleNamespace(
            read_bytes=100,
            write_bytes=200,
        )

    def fake_network():
        if io_mode == "error":
            raise OSError("Network counters unavailable")

        if io_mode == "missing":
            return None

        return SimpleNamespace(
            bytes_recv=300,
            bytes_sent=400,
        )

    monkeypatch.setattr(
        collector_module.psutil,
        "cpu_percent",
        fake_cpu_percent,
    )
    monkeypatch.setattr(
        collector_module.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            percent=50.0,
            used=8_000,
            available=8_000,
        ),
    )
    monkeypatch.setattr(
        collector_module.psutil,
        "swap_memory",
        lambda: SimpleNamespace(percent=2.0),
    )
    monkeypatch.setattr(
        collector_module.psutil,
        "disk_io_counters",
        fake_disk,
    )
    monkeypatch.setattr(
        collector_module.psutil,
        "net_io_counters",
        fake_network,
    )

    before = datetime.now(timezone.utc)
    result = TelemetryCollector().collect()
    after = datetime.now(timezone.utc)

    assert before <= result.timestamp <= after
    assert result.timestamp.utcoffset() == timedelta(0)

    assert result.cpu_percent == 25.0
    assert result.memory_percent == 50.0
    assert result.memory_used == 8_000
    assert result.memory_available == 8_000
    assert result.swap_percent == 2.0

    if io_mode == "available":
        assert result.disk_read_bytes == 100
        assert result.disk_write_bytes == 200
        assert result.network_rx_bytes == 300
        assert result.network_tx_bytes == 400
    else:
        assert result.disk_read_bytes is None
        assert result.disk_write_bytes is None
        assert result.network_rx_bytes is None
        assert result.network_tx_bytes is None