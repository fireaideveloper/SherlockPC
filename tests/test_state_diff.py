from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from sherlock.capabilities.processes.models import (
    ProcessMetric,
    ProcessSnapshot,
)
from sherlock.capabilities.state.diff import (
    StoredState,
    compare_states,
)
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_reader import (
    StateNotFoundError,
    StateReader,
)
from sherlock.storage.sqlite.state_repository import StateRepository


BASE_TIME = datetime(
    2026, 9, 24, 12, 0, 0,
    tzinfo=timezone.utc,
)


def make_state(
    offset: int,
    *,
    rss: int | None = 1000,
    cpu_seconds: float | None = 10.0,
    create_time: float = 100.25,
    skipped_count: int = 0,
) -> StateSnapshot:
    started_at = BASE_TIME + timedelta(seconds=offset)

    process = ProcessMetric(
        observed_at=started_at + timedelta(seconds=3),
        pid=100,
        create_time=create_time,
        name="demo",
        status="running",
        memory_rss=rss,
        cpu_seconds=cpu_seconds,
    )

    return StateSnapshot(
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=5),
        system=SystemMetric(
            timestamp=started_at + timedelta(seconds=1),
            cpu_percent=10.0,
            memory_percent=40.0,
            memory_used=10000,
            memory_available=15000,
            swap_percent=0.0,
            disk_read_bytes=100,
            disk_write_bytes=200,
            network_rx_bytes=300,
            network_tx_bytes=400,
        ),
        processes=ProcessSnapshot(
            started_at=started_at + timedelta(seconds=2),
            finished_at=started_at + timedelta(seconds=4),
            processes=(process,),
            skipped_count=skipped_count,
        ),
    )


def compare(
    before: StateSnapshot,
    after: StateSnapshot,
):
    return compare_states(
        StoredState(1, before),
        StoredState(2, after),
    )


@pytest.fixture
def database(tmp_path):
    database = Database(tmp_path / "sherlock.db")
    database.initialize()
    return database


def test_load_pair_restores_models(database):
    before = make_state(0, rss=None)
    before = replace(
        before,
        system=replace(
            before.system,
            network_rx_bytes=None,
        ),
    )
    after = make_state(60, rss=2000)

    repository = StateRepository(database)

    before_id = repository.save(before)
    after_id = repository.save(after)

    loaded_before, loaded_after = StateReader(
        database
    ).load_pair(before_id, after_id)

    assert loaded_before == StoredState(before_id, before)
    assert loaded_after == StoredState(after_id, after)


def test_missing_state(database):
    with pytest.raises(StateNotFoundError):
        StateReader(database).load(999)


def test_equal_values_have_zero_deltas():
    diff = compare(make_state(0), make_state(60))

    assert diff.system.cpu_percent.delta == 0
    assert diff.system.memory_used.delta == 0

    assert diff.common[0].memory_rss.delta == 0
    assert diff.common[0].cpu_seconds.raw_delta == 0
    assert diff.common[0].cpu_seconds.status == "ok"

    assert diff.only_before == ()
    assert diff.only_after == ()


@pytest.mark.parametrize("delta", [500, -500])
def test_memory_growth_and_decrease(delta):
    before = make_state(0)
    after = make_state(60, rss=1000 + delta)

    after = replace(
        after,
        system=replace(
            after.system,
            memory_used=10000 + delta,
        ),
    )

    diff = compare(before, after)

    assert diff.system.memory_used.delta == delta
    assert diff.common[0].memory_rss.delta == delta


def test_unknown_is_not_zero():
    before = make_state(
        0,
        rss=None,
        cpu_seconds=None,
    )
    after = make_state(60)

    before = replace(
        before,
        system=replace(
            before.system,
            network_rx_bytes=None,
        ),
    )

    diff = compare(before, after)

    assert diff.common[0].memory_rss.delta is None
    assert diff.common[0].cpu_seconds.raw_delta is None
    assert diff.common[0].cpu_seconds.status == "unknown"

    assert diff.system.network_rx_bytes.raw_delta is None
    assert diff.system.network_rx_bytes.status == "unknown"


def test_reused_pid_is_not_the_same_process():
    before = make_state(0, create_time=100.25)
    after = make_state(60, create_time=200.75)

    diff = compare(before, after)

    assert diff.common == ()
    assert len(diff.only_before) == 1
    assert len(diff.only_after) == 1

    assert diff.only_before[0].pid == diff.only_after[0].pid
    assert (
        diff.only_before[0].create_time
        != diff.only_after[0].create_time
    )


def test_processes_observed_only_on_one_side():
    before = make_state(0)
    after = make_state(60)

    after = replace(
        after,
        processes=replace(
            after.processes,
            processes=(),
        ),
    )

    diff = compare(before, after)

    assert len(diff.only_before) == 1
    assert diff.only_after == ()
    assert diff.common == ()

    before = replace(
        before,
        processes=replace(
            before.processes,
            processes=(),
        ),
    )
    after = make_state(60)

    diff = compare(before, after)

    assert diff.only_before == ()
    assert len(diff.only_after) == 1
    assert diff.common == ()


def test_decreased_system_counter_is_flagged():
    before = make_state(0)
    after = make_state(60)

    after = replace(
        after,
        system=replace(
            after.system,
            disk_read_bytes=20,
        ),
    )

    change = compare(before, after).system.disk_read_bytes

    assert change.raw_delta == -80
    assert change.status == "decreased"


def test_positive_system_counter_is_unverified():
    before = make_state(0)
    after = make_state(60)

    after = replace(
        after,
        system=replace(
            after.system,
            network_rx_bytes=900,
        ),
    )

    change = compare(before, after).system.network_rx_bytes

    assert change.raw_delta == 600
    assert change.status == "continuity_unverified"


@pytest.mark.parametrize(
    ("cpu_after", "expected_delta", "expected_status"),
    [
        (15.0, 5.0, "ok"),
        (3.0, -7.0, "decreased"),
    ],
)
def test_process_cpu_counter(
    cpu_after,
    expected_delta,
    expected_status,
):
    diff = compare(
        make_state(0),
        make_state(60, cpu_seconds=cpu_after),
    )

    change = diff.common[0].cpu_seconds

    assert change.raw_delta == expected_delta
    assert change.status == expected_status
    assert diff.common[0].observation_interval_seconds == 60


def test_percent_changes_are_percentage_points():
    before = make_state(0)
    after = make_state(60)

    after = replace(
        after,
        system=replace(
            after.system,
            cpu_percent=15.0,
            memory_percent=38.0,
        ),
    )

    diff = compare(before, after)

    assert diff.system.cpu_percent.delta == 5
    assert diff.system.memory_percent.delta == -2


@pytest.mark.parametrize("after_offset", [-60, 0, 3])
def test_invalid_time_order(after_offset):
    with pytest.raises(ValueError):
        compare(
            make_state(0),
            make_state(after_offset),
        )


def test_same_id_is_rejected():
    state = StoredState(1, make_state(0))

    with pytest.raises(ValueError):
        compare_states(state, state)


def test_inconsistent_nested_timestamps_are_rejected():
    before = make_state(0)
    after = make_state(60)

    after = replace(
        after,
        system=replace(
            after.system,
            timestamp=after.finished_at + timedelta(seconds=1),
        ),
    )

    with pytest.raises(ValueError):
        compare(before, after)


def test_skipped_processes_add_warning():
    diff = compare(
        make_state(0, skipped_count=3),
        make_state(60),
    )

    assert diff.before_skipped_count == 3
    assert diff.after_skipped_count == 0

    assert any(
        "coverage is incomplete" in warning
        for warning in diff.warnings
    )
