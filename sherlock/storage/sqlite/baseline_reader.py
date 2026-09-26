import math
import sqlite3
from datetime import datetime, timedelta, timezone

from sherlock.capabilities.state.baseline import (
    BaselineInput,
    BaselinePoint,
)
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_reader import StateNotFoundError


POINT_COLUMNS = """
    state.id AS state_id,
    metric.timestamp,
    metric.cpu_percent,
    metric.memory_percent,
    metric.memory_used,
    metric.memory_available,
    metric.swap_percent
"""


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    )


def _point_from_row(row: sqlite3.Row) -> BaselinePoint:
    return BaselinePoint(
        state_id=row["state_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        cpu_percent=row["cpu_percent"],
        memory_percent=row["memory_percent"],
        memory_used=row["memory_used"],
        memory_available=row["memory_available"],
        swap_percent=row["swap_percent"],
    )


class BaselineReader:
    def __init__(self, database: Database) -> None:
        self.database = database

    def load(
        self,
        target_id: int,
        *,
        hours: float = 24.0,
        limit: int = 200,
    ) -> BaselineInput:
        if target_id < 1:
            raise ValueError("target_id must be positive")

        if not math.isfinite(hours) or hours <= 0:
            raise ValueError("hours must be finite and positive")

        if limit < 1:
            raise ValueError("limit must be positive")

        with self.database.connection() as connection:
            connection.execute("BEGIN")

            try:
                result = self._read(
                    connection,
                    target_id,
                    hours=hours,
                    limit=limit,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return result

    @staticmethod
    def _read(
        connection: sqlite3.Connection,
        target_id: int,
        *,
        hours: float,
        limit: int,
    ) -> BaselineInput:
        target_row = connection.execute(
            f"""
            SELECT
                {POINT_COLUMNS},
                state.started_at,
                state.finished_at
            FROM state_snapshots AS state
            JOIN system_metrics AS metric
                ON metric.id = state.system_metric_id
            WHERE state.id = ?
            """,
            (target_id,),
        ).fetchone()

        if target_row is None:
            raise StateNotFoundError(
                f"State snapshot {target_id} was not found "
                "or has no linked system metric"
            )

        target = _point_from_row(target_row)

        cutoff = datetime.fromisoformat(
            target_row["started_at"]
        )
        finished_at = datetime.fromisoformat(
            target_row["finished_at"]
        )

        if not cutoff <= target.timestamp <= finished_at:
            raise ValueError(
                "Target timestamps are inconsistent"
            )

        try:
            window_start = cutoff - timedelta(hours=hours)
        except OverflowError as error:
            raise ValueError(
                "Requested history window is too large"
            ) from error

        rows = connection.execute(
            f"""
            SELECT {POINT_COLUMNS}
            FROM state_snapshots AS state
            JOIN system_metrics AS metric
                ON metric.id = state.system_metric_id
            WHERE state.id != ?
              AND metric.timestamp >= ?
              AND metric.timestamp < ?
              AND state.finished_at <= ?
              AND state.started_at <= metric.timestamp
              AND metric.timestamp <= state.finished_at
            ORDER BY metric.timestamp DESC, state.id DESC
            LIMIT ?
            """,
            (
                target_id,
                _iso_utc(window_start),
                _iso_utc(cutoff),
                _iso_utc(cutoff),
                limit,
            ),
        ).fetchall()

        return BaselineInput(
            target=target,
            history=tuple(
                _point_from_row(row)
                for row in rows
            ),
            window_start=window_start,
            cutoff=cutoff,
            limit=limit,
        )
