import argparse
from pathlib import Path

from sherlock.capabilities.state.collector import StateCollector
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.state_repository import StateRepository


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect a state snapshot or list stored snapshots."
    )

    parser.add_argument(
        "--list",
        dest="list_snapshots",
        action="store_true",
        help="List stored snapshots instead of collecting.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of listed snapshots. Default: 10.",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be positive")

    database = Database(
        Path.cwd() / "data" / "sherlock.db"
    )
    database.initialize()

    repository = StateRepository(database)

    if args.list_snapshots:
        rows = repository.recent(limit=args.limit)

        if not rows:
            print("No stored state snapshots.")
            return

        print("\nNewest stored state snapshots first:\n")

        for row in rows:
            print(f"State ID         {row['id']}")
            print(f"Started UTC      {row['started_at']}")
            print(f"Finished UTC     {row['finished_at']}")
            print(f"CPU              {row['cpu_percent']:.1f}%")
            print(f"Memory           {row['memory_percent']:.1f}%")
            print(f"Processes        {row['process_count']}")
            print(f"Skipped          {row['skipped_count']}")
            print()

        return

    print("\nCollecting system and process observations...")

    snapshot = StateCollector().collect()
    state_id = repository.save(snapshot)

    print(f"State ID         {state_id}")
    print(f"Started UTC      {snapshot.started_at.isoformat()}")
    print(f"Finished UTC     {snapshot.finished_at.isoformat()}")
    print(f"CPU              {snapshot.system.cpu_percent:.1f}%")
    print(f"Memory           {snapshot.system.memory_percent:.1f}%")
    print(f"Processes        {len(snapshot.processes.processes)}")
    print(f"Skipped          {snapshot.processes.skipped_count}")
    print(f"Schema version   {database.get_schema_version()}")
    print("Status           SAVED")
    print()


if __name__ == "__main__":
    main()
