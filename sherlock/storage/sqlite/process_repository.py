import sqlite3
from datetime import datetime, timezone

from sherlock.capabilities.processes.models import ProcessSnapshot

from .database import Database


def to_utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
    )


class ProcessRepository:

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, snapshot: ProcessSnapshot) -> int:
        with self.database.connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO process_snapshots (
                        started_at,
                        finished_at,
                        skipped_count
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        to_utc_text(snapshot.started_at),
                        to_utc_text(snapshot.finished_at),
                        snapshot.skipped_count,
                    ),
                )

                snapshot_id = cursor.lastrowid

                if snapshot_id is None:
                    raise RuntimeError("Snapshot ID was not returned")

                connection.executemany(
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            snapshot_id,
                            to_utc_text(metric.observed_at),
                            metric.pid,
                            metric.create_time,
                            metric.name,
                            metric.status,
                            metric.memory_rss,
                            metric.cpu_seconds,
                        )
                        for metric in snapshot.processes
                    ],
                )

        return snapshot_id

    def history(
        self,
        pid: int,
        limit: int = 20,
    ) -> list[sqlite3.Row]:

        if pid < 0:
            raise ValueError("pid must not be negative")

        if limit < 1:
            raise ValueError("limit must be positive")

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    snapshot_id,
                    observed_at,
                    pid,
                    create_time,
                    name,
                    status,
                    memory_rss,
                    cpu_seconds
                FROM process_metrics
                WHERE pid = ?
                ORDER BY snapshot_id DESC
                LIMIT ?
                """,
                (pid, limit),
            ).fetchall()

        return rows
