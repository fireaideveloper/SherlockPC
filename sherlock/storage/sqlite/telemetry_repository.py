import sqlite3
from dataclasses import asdict
from datetime import timezone

from sherlock.capabilities.telemetry.models import SystemMetric

from .database import Database


class TelemetryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, metric: SystemMetric) -> int:
        with self.database.connection() as connection:
            with connection:
                metric_id = self.insert(connection, metric)

        return metric_id

    def insert(
        self,
        connection: sqlite3.Connection,
        metric: SystemMetric,
    ) -> int:

        values = asdict(metric)

        values["timestamp"] = (
            metric.timestamp
            .astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
        )

        cursor = connection.execute(
            """
            INSERT INTO system_metrics (
                timestamp,
                cpu_percent,
                memory_percent,
                memory_used,
                memory_available,
                swap_percent,
                disk_read_bytes,
                disk_write_bytes,
                network_rx_bytes,
                network_tx_bytes
            )
            VALUES (
                :timestamp,
                :cpu_percent,
                :memory_percent,
                :memory_used,
                :memory_available,
                :swap_percent,
                :disk_read_bytes,
                :disk_write_bytes,
                :network_rx_bytes,
                :network_tx_bytes
            )
            """,
            values,
        )

        metric_id = cursor.lastrowid

        if metric_id is None:
            raise RuntimeError("Metric ID was not returned")

        return metric_id
