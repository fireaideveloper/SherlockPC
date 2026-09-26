from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from sherlock.capabilities.processes.models import ProcessSnapshot
from sherlock.capabilities.state.baseline import (
    BaselineInput,
    BaselinePoint,
    build_baseline,
)
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.storage.sqlite.baseline_reader import BaselineReader
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_reader import StateNotFoundError
from sherlock.storage.sqlite.state_repository import StateRepository
from sherlock.storage.sqlite.telemetry_repository import TelemetryRepository


BASE = datetime(
    2026, 9, 25, 12, 0, 0,
    tzinfo=timezone.utc,
)


def make_point(
    state_id: int,
    seconds: int,
    cpu: float = 10.0,
) -> BaselinePoint:
    return BaselinePoint(
        state_id=state_id,
        timestamp=BASE + timedelta(seconds=seconds),
        cpu_percent=cpu,
        memory_percent=40.0,
        memory_used=10000,
        memory_available=15000,
        swap_percent=0.0,
    )


def make_input(
    history: tuple[BaselinePoint, ...],
) -> BaselineInput:
    return BaselineInput(
        target=make_point(100, 601, cpu=90.0),
        history=history,
        window_start=BASE - timedelta(hours=1),
        cutoff=BASE + timedelta(seconds=600),
        limit=200,
    )


def make_snapshot(seconds: int) -> StateSnapshot:
    started = BASE + timedelta(seconds=seconds)

    return StateSnapshot(
        started_at=started,
        finished_at=started + timedelta(seconds=5),
        system=SystemMetric(
            timestamp=started + timedelta(seconds=1),
            cpu_percent=10.0,
            memory_percent=40.0,
            memory_used=10000,
            memory_available=15000,
            swap_percent=0.0,
            disk_read_bytes=None,
            disk_write_bytes=None,
            network_rx_bytes=None,
            network_tx_bytes=None,
        ),
        processes=ProcessSnapshot(
            started_at=started + timedelta(seconds=2),
            finished_at=started + timedelta(seconds=4),
            processes=(),
            skipped_count=0,
        ),
    )


@pytest.fixture
def database(tmp_path):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()
    return database


def test_statistics_and_target_exclusion():
    data = make_input(
        (
            make_point(1, 0, cpu=10),
            make_point(2, 60, cpu=20),
            make_point(3, 120, cpu=30),
        )
    )

    report = build_baseline(
        data,
        min_samples=3,
        min_span_seconds=120,
    )
    cpu = report.metrics[0]

    assert report.status == "enough_data"
    assert report.history_ids == (1, 2, 3)
    assert report.sample_count == 3

    assert cpu.current == 90
    assert cpu.mean == 20
    assert cpu.median == 20
    assert cpu.minimum == 10
    assert cpu.maximum == 30
    assert cpu.p10 == pytest.approx(12)
    assert cpu.p90 == pytest.approx(28)
    assert cpu.stddev == pytest.approx((200 / 3) ** 0.5)
    assert cpu.delta_from_median == 70


def test_empty_history_is_insufficient():
    report = build_baseline(make_input(()))

    assert report.status == "insufficient_data"
    assert report.sample_count == 0
    assert report.first_observed_at is None

    for metric in report.metrics:
        assert metric.mean is None
        assert metric.median is None
        assert metric.delta_from_median is None


def test_one_observation_is_insufficient():
    report = build_baseline(
        make_input((make_point(1, 0),))
    )

    assert report.status == "insufficient_data"
    assert report.metrics[0].stddev == 0
    assert report.largest_gap_seconds is None


def test_constant_values_have_zero_spread():
    report = build_baseline(
        make_input(
            (
                make_point(1, 0),
                make_point(2, 60),
            )
        ),
        min_samples=2,
        min_span_seconds=60,
    )

    assert report.status == "enough_data"
    assert report.metrics[0].stddev == 0
    assert report.metrics[0].p10 == 10
    assert report.metrics[0].p90 == 10


def test_enough_samples_but_short_span():
    report = build_baseline(
        make_input(
            (
                make_point(1, 0),
                make_point(2, 1),
                make_point(3, 2),
            )
        ),
        min_samples=3,
        min_span_seconds=300,
    )

    assert report.status == "insufficient_data"
    assert report.span_seconds == 2
    assert len(report.reasons) == 1


def test_history_is_sorted_and_gaps_are_reported():
    report = build_baseline(
        make_input(
            (
                make_point(3, 120),
                make_point(1, 0),
                make_point(2, 30),
            )
        )
    )

    assert report.history_ids == (1, 2, 3)
    assert report.span_seconds == 120
    assert report.largest_gap_seconds == 90


def test_target_in_history_is_rejected():
    data = make_input(
        (make_point(100, 0),)
    )

    with pytest.raises(ValueError):
        build_baseline(data)


def test_duplicate_history_id_is_rejected():
    data = make_input(
        (
            make_point(1, 0),
            make_point(1, 60),
        )
    )

    with pytest.raises(ValueError):
        build_baseline(data)


@pytest.mark.parametrize("seconds", [-3601, 600, 700])
def test_outside_window_is_rejected(seconds):
    data = make_input(
        (make_point(1, seconds),)
    )

    with pytest.raises(ValueError):
        build_baseline(data)


def test_non_finite_value_is_rejected():
    with pytest.raises(ValueError):
        make_point(1, 0, cpu=float("nan"))


def test_reader_filters_window_and_future(database):
    repository = StateRepository(database)

    repository.save(make_snapshot(-7200))
    historical_id = repository.save(make_snapshot(0))
    target_id = repository.save(make_snapshot(600))
    repository.save(make_snapshot(1200))

    data = BaselineReader(database).load(
        target_id,
        hours=1,
    )

    assert data.target.state_id == target_id
    assert tuple(
        point.state_id for point in data.history
    ) == (historical_id,)


def test_reader_excludes_overlapping_collection(database):
    repository = StateRepository(database)

    repository.save(make_snapshot(598))
    target_id = repository.save(make_snapshot(600))

    data = BaselineReader(database).load(target_id)

    assert data.history == ()


def test_reader_uses_time_not_id_order(database):
    repository = StateRepository(database)

    target_id = repository.save(make_snapshot(600))

    # Более ранний снимок записан в базу позже целевого.
    historical_id = repository.save(make_snapshot(0))

    data = BaselineReader(database).load(target_id)

    assert historical_id > target_id
    assert data.history[0].state_id == historical_id


def test_reader_limit_selects_latest_observations(database):
    repository = StateRepository(database)

    repository.save(make_snapshot(0))
    second_id = repository.save(make_snapshot(60))
    third_id = repository.save(make_snapshot(120))
    target_id = repository.save(make_snapshot(600))

    data = BaselineReader(database).load(
        target_id,
        limit=2,
    )

    assert tuple(
        point.state_id for point in data.history
    ) == (third_id, second_id)


def test_reader_ignores_standalone_system_metrics(database):
    standalone = make_snapshot(0).system
    TelemetryRepository(database).save(standalone)

    target_id = StateRepository(database).save(
        make_snapshot(600)
    )

    data = BaselineReader(database).load(target_id)

    assert data.history == ()


def test_reader_missing_target(database):
    with pytest.raises(StateNotFoundError):
        BaselineReader(database).load(999)


def test_reader_includes_exact_lower_boundary(database):
    repository = StateRepository(database)

    # timestamp = BASE + 1 секунда.
    historical_id = repository.save(make_snapshot(0))

    # cutoff = BASE + 3601 секунда.
    # При hours=1 нижняя граница = BASE + 1 секунда.
    target_id = repository.save(make_snapshot(3601))

    data = BaselineReader(database).load(
        target_id,
        hours=1,
    )

    assert data.history[0].state_id == historical_id


def test_negative_memory_difference_is_preserved():
    data = make_input(
        (
            make_point(1, 0),
            make_point(2, 60),
        )
    )

    data = replace(
        data,
        target=replace(
            data.target,
            memory_used=8000,
        ),
    )

    report = build_baseline(data)

    memory = next(
        metric
        for metric in report.metrics
        if metric.name == "memory_used"
    )

    assert memory.delta_from_median == -2000
