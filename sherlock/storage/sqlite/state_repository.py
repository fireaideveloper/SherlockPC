import sqlite3
from datetime import datetime, timezone

from sherlock.capabilities.state.models import StateSnapshot

from .database import Database
from .process_repository import ProcessRepository
from .telemetry_repository import TelemetryRepository


def to_utc_text(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
    )


class StateRepository:

    def __init__(self, database: Database) -> None:
        self.database = database

        self.telemetry_repository = TelemetryRepository(database)
        self.process_repository = ProcessRepository(database)

    def save(self, snapshot: StateSnapshot) -> int:
        with self.database.connection() as connection:
            with connection:
                system_metric_id = self.telemetry_repository.insert(
                    connection,
                    snapshot.system,
                )

                process_snapshot_id = self.process_repository.insert(
                    connection,
                    snapshot.processes,
                )

                cursor = connection.execute(
                    """
                    INSERT INTO state_snapshots (
                        started_at,
                        finished_at,
                        system_metric_id,
                        process_snapshot_id
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        to_utc_text(snapshot.started_at),
                        to_utc_text(snapshot.finished_at),
                        system_metric_id,
                        process_snapshot_id,
                    ),
                )

                state_id = cursor.lastrowid

                if state_id is None:
                    raise RuntimeError("State ID was not returned")

        return state_id

    def recent(self, limit: int = 10) -> list[sqlite3.Row]:

        if limit < 1:
            raise ValueError("limit must be positive")

        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    state.id,
                    state.started_at,
                    state.finished_at,

                    system.cpu_percent,
                    system.memory_percent,

                    processes.skipped_count,

                    (
                        SELECT COUNT(*)
                        FROM process_metrics AS metric
                        WHERE metric.snapshot_id =
                            state.process_snapshot_id
                    ) AS process_count

                FROM state_snapshots AS state

                JOIN system_metrics AS system
                    ON system.id = state.system_metric_id

                JOIN process_snapshots AS processes
                    ON processes.id = state.process_snapshot_id

                ORDER BY state.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return rows
