import argparse
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sherlock.capabilities.state.diff import (
    StateDiff,
    compare_states,
)
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_reader import (
    StateNotFoundError,
    StateReader,
)


MIB = 1024 * 1024


def json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()

    raise TypeError(
        f"Cannot serialize {type(value).__name__}"
    )


def print_summary(diff: StateDiff) -> None:
    print(f"State comparison: {diff.before_id} -> {diff.after_id}")
    print(
        "System observation interval: "
        f"{diff.system_interval_seconds:.3f} s"
    )

    print(
        "Collection windows: "
        f"{diff.before_started_at.isoformat()} .. "
        f"{diff.before_finished_at.isoformat()}"
    )
    print(
        "                    "
        f"{diff.after_started_at.isoformat()} .. "
        f"{diff.after_finished_at.isoformat()}"
    )

    print()

    for name in (
        "cpu_percent",
        "memory_percent",
        "swap_percent",
    ):
        change = getattr(diff.system, name)
        delta = (
            "unknown"
            if change.delta is None
            else f"{change.delta:+.2f} pp"
        )

        print(
            f"{name}: {change.before} -> {change.after}; "
            f"delta={delta}"
        )

    for name in ("memory_used", "memory_available"):
        change = getattr(diff.system, name)
        delta = (
            "unknown"
            if change.delta is None
            else f"{change.delta / MIB:+.2f} MiB"
        )

        print(f"{name}: delta={delta}")

    print()

    for name in (
        "disk_read_bytes",
        "disk_write_bytes",
        "network_rx_bytes",
        "network_tx_bytes",
    ):
        change = getattr(diff.system, name)

        print(
            f"{name}: raw_delta={change.raw_delta}; "
            f"status={change.status}"
        )

    print()
    print(f"Processes only before: {len(diff.only_before)}")
    print(f"Processes only after:  {len(diff.only_after)}")
    print(f"Matched processes:     {len(diff.common)}")
    print(
        "Skipped observations: "
        f"{diff.before_skipped_count} -> "
        f"{diff.after_skipped_count}"
    )

    for label, processes in (
        ("Only before", diff.only_before),
        ("Only after", diff.only_after),
    ):
        print()
        print(f"{label}, first 10:")

        for process in processes[:10]:
            print(
                f"  PID={process.pid} "
                f"created={process.create_time} "
                f"name={process.name!r}"
            )

    changed_rss = [
        process
        for process in diff.common
        if process.memory_rss.delta is not None
        and process.memory_rss.delta != 0
    ]

    changed_rss.sort(
        key=lambda process: abs(process.memory_rss.delta),
        reverse=True,
    )

    print()
    print("Largest absolute RSS changes, first 10:")

    for process in changed_rss[:10]:
        delta_mib = process.memory_rss.delta / MIB

        print(
            f"  PID={process.after.pid} "
            f"name={process.after.name!r} "
            f"RSS={delta_mib:+.2f} MiB"
        )

    print()
    print("Use --json for all processes and CPU-time changes.")

    print()
    print("Limitations:")

    for warning in diff.warnings:
        print(f"  - {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two stored SherlockPC state snapshots"
    )

    parser.add_argument(
        "--before",
        type=int,
        required=True,
        help="ID of the earlier state snapshot",
    )

    parser.add_argument(
        "--after",
        type=int,
        required=True,
        help="ID of the later state snapshot",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete structured result as JSON",
    )

    args = parser.parse_args()

    database = Database(
        Path.cwd() / "data" / "sherlock.db"
    )

    try:
        database.initialize()

        before, after = StateReader(database).load_pair(
            args.before,
            args.after,
        )

        diff = compare_states(before, after)

    except (
        StateNotFoundError,
        ValueError,
        sqlite3.Error,
    ) as error:
        parser.exit(
            status=1,
            message=f"Error: {error}\n",
        )

    if args.json:
        print(
            json.dumps(
                asdict(diff),
                ensure_ascii=False,
                indent=2,
                default=json_default,
            )
        )
    else:
        print_summary(diff)


if __name__ == "__main__":
    main()
