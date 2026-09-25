import sqlite3
from datetime import datetime

from sherlock.capabilities.processes.models import (
    ProcessMetric,
    ProcessSnapshot,
)
from sherlock.capabilities.state.diff import StoredState
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.storage.sqlite.database import Database


class StateNotFoundError(LookupError):
    pass


class StateReader:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load(self, state_id: int) -> StoredState:
        return self._load_many((state_id,))[0]

    def load_pair(
        self,
        before_id: int,
        after_id: int,
    ) -> tuple[StoredState, StoredState]:
        before, after = self._load_many(
            (before_id, after_id)
        )
        return before, after

    def _load_many(
        self,
        state_ids: tuple[int, ...],
    ) -> tuple[StoredState, ...]:
        if any(state_id < 1 for state_id in state_ids):
            raise ValueError("State IDs must be positive")

        with self.database.connection() as connection:
           
            connection.execute("BEGIN")

            try:
                result = tuple(
                    self._read(connection, state_id)
                    for state_id in state_ids
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return result

    @staticmethod
    def _read(
        connection: sqlite3.Connection,
        state_id: int,
    ) -> StoredState:
        state_row = connection.execute(
            """
            SELECT *
            FROM state_snapshots
            WHERE id = ?
            """,
            (state_id,),
        ).fetchone()

        if state_row is None:
            raise StateNotFoundError(
                f"State snapshot {state_id} was not found"
            )

        system_row = connection.execute(
            """
            SELECT *
            FROM system_metrics
            WHERE id = ?
            """,
            (state_row["system_metric_id"],),
        ).fetchone()

        process_snapshot_row = connection.execute(
            """
            SELECT *
            FROM process_snapshots
            WHERE id = ?
            """,
            (state_row["process_snapshot_id"],),
        ).fetchone()

        if system_row is None or process_snapshot_row is None:
            raise ValueError(
                f"State snapshot {state_id} has missing linked data"
            )

        process_rows = connection.execute(
            """
            SELECT
                observed_at,
                pid,
                create_time,
                name,
                status,
                memory_rss,
                cpu_seconds
            FROM process_metrics
            WHERE snapshot_id = ?
            ORDER BY pid, create_time
            """,
            (state_row["process_snapshot_id"],),
        ).fetchall()

        system = SystemMetric(
            timestamp=datetime.fromisoformat(
                system_row["timestamp"]
            ),
            cpu_percent=system_row["cpu_percent"],
            memory_percent=system_row["memory_percent"],
            memory_used=system_row["memory_used"],
            memory_available=system_row["memory_available"],
            swap_percent=system_row["swap_percent"],
            disk_read_bytes=system_row["disk_read_bytes"],
            disk_write_bytes=system_row["disk_write_bytes"],
            network_rx_bytes=system_row["network_rx_bytes"],
            network_tx_bytes=system_row["network_tx_bytes"],
        )

        processes = tuple(
            ProcessMetric(
                observed_at=datetime.fromisoformat(
                    row["observed_at"]
                ),
                pid=row["pid"],
                create_time=row["create_time"],
                name=row["name"],
                status=row["status"],
                memory_rss=row["memory_rss"],
                cpu_seconds=row["cpu_seconds"],
            )
            for row in process_rows
        )

        process_snapshot = ProcessSnapshot(
            started_at=datetime.fromisoformat(
                process_snapshot_row["started_at"]
            ),
            finished_at=datetime.fromisoformat(
                process_snapshot_row["finished_at"]
            ),
            processes=processes,
            skipped_count=process_snapshot_row["skipped_count"],
        )

        snapshot = StateSnapshot(
            started_at=datetime.fromisoformat(
                state_row["started_at"]
            ),
            finished_at=datetime.fromisoformat(
                state_row["finished_at"]
            ),
            system=system,
            processes=process_snapshot,
        )

        return StoredState(
            state_id=state_id,
            snapshot=snapshot,
        )
