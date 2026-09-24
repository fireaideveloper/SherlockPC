import argparse
from pathlib import Path

from sherlock.capabilities.processes.collector import ProcessCollector
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.process_repository import ProcessRepository


def format_memory(value: int | None) -> str:
    if value is None:
        return "N/A"

    return f"{value / (1024 ** 2):.1f} MiB"


def format_cpu(value: float | None) -> str:
    if value is None:
        return "N/A"

    return f"{value:.2f} s"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect process snapshots or read stored history."
    )
    parser.add_argument(
        "--pid",
        type=int,
        help="Read stored history for this PID instead of collecting.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of history rows. Default: 20.",
    )

    args = parser.parse_args()

    if args.pid is not None and args.pid < 0:
        parser.error("--pid must not be negative")

    if args.limit < 1:
        parser.error("--limit must be positive")

    database = Database(
        Path.cwd() / "data" / "sherlock.db"
    )
    database.initialize()

    repository = ProcessRepository(database)

    if args.pid is not None:
        rows = repository.history(
            pid=args.pid,
            limit=args.limit,
        )

        print(f"\nStored history for PID {args.pid}")
        print("Newest stored observations first.\n")

        if not rows:
            print("No stored observations.")
            return

        for row in rows:
            print(
                f"Snapshot {row['snapshot_id']} | "
                f"{row['observed_at']}"
            )
            print(
                f"PID {row['pid']} | "
                f"Created epoch: {row['create_time']!r} | "
                f"Name: {row['name'] or 'N/A'}"
            )
            print(
                f"Status: {row['status'] or 'N/A'} | "
                f"RAM: {format_memory(row['memory_rss'])} | "
                f"CPU total: {format_cpu(row['cpu_seconds'])}"
            )
            print()

        return

    print("\nCollecting process snapshot...")

    snapshot = ProcessCollector().collect()
    snapshot_id = repository.save(snapshot)

    incomplete_count = sum(
        any(
            value is None
            for value in (
                metric.name,
                metric.status,
                metric.memory_rss,
                metric.cpu_seconds,
            )
        )
        for metric in snapshot.processes
    )

    print(f"Started UTC       {snapshot.started_at.isoformat()}")
    print(f"Finished UTC      {snapshot.finished_at.isoformat()}")
    print(f"Schema version    {database.get_schema_version()}")
    print(f"Snapshot ID       {snapshot_id}")
    print(f"Saved processes   {len(snapshot.processes)}")
    print(f"Partial records   {incomplete_count}")
    print(f"Skipped processes {snapshot.skipped_count}")
    print("Status            SAVED")

    top_memory = sorted(
        (
            metric
            for metric in snapshot.processes
            if metric.memory_rss is not None
        ),
        key=lambda metric: metric.memory_rss,
        reverse=True,
    )[:10]

    print("\nTop processes by observed RAM:")
    print(f"{'PID':>8}  {'RAM':>14}  {'CPU total':>14}  Name")

    for metric in top_memory:
        print(
            f"{metric.pid:>8}  "
            f"{format_memory(metric.memory_rss):>14}  "
            f"{format_cpu(metric.cpu_seconds):>14}  "
            f"{metric.name or 'N/A'}"
        )

    print()


if __name__ == "__main__":
    main()
