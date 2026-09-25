from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sherlock.capabilities.processes.models import ProcessMetric
from sherlock.capabilities.state.models import StateSnapshot


Number = int | float

CounterStatus = Literal[
    "unknown",
    "decreased",
    "continuity_unverified",
    "ok",
]


@dataclass(frozen=True, slots=True)
class StoredState:

    state_id: int
    snapshot: StateSnapshot

    def __post_init__(self) -> None:
        if self.state_id < 1:
            raise ValueError("state_id must be positive")


@dataclass(frozen=True, slots=True)
class ValueChange:
    before: Number | None
    after: Number | None
    delta: Number | None


@dataclass(frozen=True, slots=True)
class CounterChange:
    before: Number | None
    after: Number | None

    raw_delta: Number | None

    status: CounterStatus


@dataclass(frozen=True, slots=True)
class SystemDiff:
    cpu_percent: ValueChange
    memory_percent: ValueChange
    memory_used: ValueChange
    memory_available: ValueChange
    swap_percent: ValueChange

    disk_read_bytes: CounterChange
    disk_write_bytes: CounterChange
    network_rx_bytes: CounterChange
    network_tx_bytes: CounterChange


@dataclass(frozen=True, slots=True)
class ProcessDiff:
    before: ProcessMetric
    after: ProcessMetric

    memory_rss: ValueChange
    cpu_seconds: CounterChange

    observation_interval_seconds: float


@dataclass(frozen=True, slots=True)
class StateDiff:
    before_id: int
    after_id: int

    before_started_at: datetime
    before_finished_at: datetime
    after_started_at: datetime
    after_finished_at: datetime

    system_interval_seconds: float

    before_skipped_count: int
    after_skipped_count: int

    system: SystemDiff

    only_before: tuple[ProcessMetric, ...]
    only_after: tuple[ProcessMetric, ...]
    common: tuple[ProcessDiff, ...]

    warnings: tuple[str, ...]


def value_change(
    before: Number | None,
    after: Number | None,
) -> ValueChange:
    delta = None

    if before is not None and after is not None:
        delta = after - before

    return ValueChange(
        before=before,
        after=after,
        delta=delta,
    )


def counter_change(
    before: Number | None,
    after: Number | None,
    *,
    same_process: bool = False,
) -> CounterChange:
    if before is None or after is None:
        return CounterChange(
            before=before,
            after=after,
            raw_delta=None,
            status="unknown",
        )

    raw_delta = after - before

    if raw_delta < 0:
        status: CounterStatus = "decreased"
    elif same_process:
        status = "ok"
    else:
        status = "continuity_unverified"

    return CounterChange(
        before=before,
        after=after,
        raw_delta=raw_delta,
        status=status,
    )


def _validate_snapshot(snapshot: StateSnapshot) -> None:

    processes = snapshot.processes

    if not (
        snapshot.started_at
        <= snapshot.system.timestamp
        <= processes.started_at
        <= processes.finished_at
        <= snapshot.finished_at
    ):
        raise ValueError(
            "Snapshot timestamps are inconsistent"
        )

    seen_pids: set[int] = set()

    for process in processes.processes:
        if not (
            processes.started_at
            <= process.observed_at
            <= processes.finished_at
        ):
            raise ValueError(
                "Process observation is outside snapshot boundaries"
            )

        if process.pid in seen_pids:
            raise ValueError(
                f"Duplicate PID in snapshot: {process.pid}"
            )

        seen_pids.add(process.pid)


def compare_states(
    before: StoredState,
    after: StoredState,
) -> StateDiff:

    if before.state_id == after.state_id:
        raise ValueError("Choose two different state IDs")

    old = before.snapshot
    new = after.snapshot

    _validate_snapshot(old)
    _validate_snapshot(new)

    if (
        new.started_at <= old.started_at
        or new.started_at < old.finished_at
    ):
        raise ValueError(
            "The second snapshot must follow the first "
            "without overlapping collection intervals"
        )

    system_interval = (
        new.system.timestamp - old.system.timestamp
    ).total_seconds()

    if system_interval <= 0:
        raise ValueError(
            "System observation interval must be positive"
        )

    old_processes = {
        (process.pid, process.create_time): process
        for process in old.processes.processes
    }

    new_processes = {
        (process.pid, process.create_time): process
        for process in new.processes.processes
    }

    old_keys = set(old_processes)
    new_keys = set(new_processes)

    only_before = tuple(
        old_processes[key]
        for key in sorted(old_keys - new_keys)
    )

    only_after = tuple(
        new_processes[key]
        for key in sorted(new_keys - old_keys)
    )

    common: list[ProcessDiff] = []

    for key in sorted(old_keys & new_keys):
        old_process = old_processes[key]
        new_process = new_processes[key]

        interval = (
            new_process.observed_at - old_process.observed_at
        ).total_seconds()

        if interval <= 0:
            raise ValueError(
                f"Process observation interval must be positive: {key}"
            )

        common.append(
            ProcessDiff(
                before=old_process,
                after=new_process,
                memory_rss=value_change(
                    old_process.memory_rss,
                    new_process.memory_rss,
                ),
                cpu_seconds=counter_change(
                    old_process.cpu_seconds,
                    new_process.cpu_seconds,
                    same_process=True,
                ),
                observation_interval_seconds=interval,
            )
        )

    system = SystemDiff(
        cpu_percent=value_change(
            old.system.cpu_percent,
            new.system.cpu_percent,
        ),
        memory_percent=value_change(
            old.system.memory_percent,
            new.system.memory_percent,
        ),
        memory_used=value_change(
            old.system.memory_used,
            new.system.memory_used,
        ),
        memory_available=value_change(
            old.system.memory_available,
            new.system.memory_available,
        ),
        swap_percent=value_change(
            old.system.swap_percent,
            new.system.swap_percent,
        ),
        disk_read_bytes=counter_change(
            old.system.disk_read_bytes,
            new.system.disk_read_bytes,
        ),
        disk_write_bytes=counter_change(
            old.system.disk_write_bytes,
            new.system.disk_write_bytes,
        ),
        network_rx_bytes=counter_change(
            old.system.network_rx_bytes,
            new.system.network_rx_bytes,
        ),
        network_tx_bytes=counter_change(
            old.system.network_tx_bytes,
            new.system.network_tx_bytes,
        ),
    )

    warnings = [
        "Snapshots contain sequential observations, not atomic measurements.",
        "Presence in only one snapshot does not prove process start or exit.",
        "System counter continuity is unverified; raw deltas are not traffic totals.",
        "Intervals use wall-clock timestamps; clock adjustments are not detected.",
    ]

    if (
        old.processes.skipped_count > 0
        or new.processes.skipped_count > 0
    ):
        warnings.append(
            "Some processes were skipped; process coverage is incomplete."
        )

    return StateDiff(
        before_id=before.state_id,
        after_id=after.state_id,
        before_started_at=old.started_at,
        before_finished_at=old.finished_at,
        after_started_at=new.started_at,
        after_finished_at=new.finished_at,
        system_interval_seconds=system_interval,
        before_skipped_count=old.processes.skipped_count,
        after_skipped_count=new.processes.skipped_count,
        system=system,
        only_before=only_before,
        only_after=only_after,
        common=tuple(common),
        warnings=tuple(warnings),
    )
