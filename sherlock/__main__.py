from pathlib import Path

from sherlock import __version__
from sherlock.capabilities.telemetry.collector import TelemetryCollector
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.telemetry_repository import (
    TelemetryRepository,
)


def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"

    return f"{value / (1024 ** 3):.3f} GiB"


def main() -> None:
    database_path = Path.cwd() / "data" / "sherlock.db"

    database = Database(database_path)
    database.initialize()

    collector = TelemetryCollector()
    repository = TelemetryRepository(database)

    print("\nSHERLOCKPC")
    print("Collecting system metrics...\n")

    metric = collector.collect()
    metric_id = repository.save(metric)

    print(f"Version          {__version__}")
    print(f"Timestamp UTC    {metric.timestamp.isoformat()}")
    print()

    print(f"CPU (1 s)        {metric.cpu_percent:.1f}%")
    print(f"Memory           {metric.memory_percent:.1f}%")
    print(f"Memory used      {format_bytes(metric.memory_used)}")
    print(f"Available        {format_bytes(metric.memory_available)}")
    print(f"Swap             {metric.swap_percent:.1f}%")
    print()

    print("Cumulative I/O counters:")
    print(f"Disk read        {format_bytes(metric.disk_read_bytes)}")
    print(f"Disk write       {format_bytes(metric.disk_write_bytes)}")
    print(f"Network RX       {format_bytes(metric.network_rx_bytes)}")
    print(f"Network TX       {format_bytes(metric.network_tx_bytes)}")
    print()

    print(f"Database         {database_path}")
    print(f"Schema version   {database.get_schema_version()}")
    print(f"Saved metric ID  {metric_id}")

    optional_values = (
        metric.disk_read_bytes,
        metric.disk_write_bytes,
        metric.network_rx_bytes,
        metric.network_tx_bytes,
    )

    if any(value is None for value in optional_values):
        print("Status           SAVED (some counters unavailable)")
    else:
        print("Status           SAVED")

    print()


if __name__ == "__main__":
    main()