from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sherlock.storage.sqlite import Database


class HistoryStore:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _generation(connection) -> str:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'desktop_history_generation'"
        ).fetchone()
        return row["value"] if row else "initial"

    def info(self) -> dict:
        path = self.database.path.resolve()
        with self.database.connection() as connection:
            connection.execute("BEGIN")
            count = connection.execute("SELECT COUNT(*) FROM state_snapshots").fetchone()[0]
            generation = self._generation(connection)
        size = 0
        for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            try:
                size += candidate.stat().st_size
            except FileNotFoundError:
                pass
        return {"database_path": str(path), "state_count": count,
                "size_bytes": size, "generation": generation}

    def page(self, page: int = 0, page_size: int = 5, anchor_id: int | None = None) -> dict:
        if page < 0 or not 1 <= page_size <= 50:
            raise ValueError("Invalid history page")
        if anchor_id is not None and anchor_id < 0:
            raise ValueError("Invalid history anchor")
        with self.database.connection() as connection:
            connection.execute("BEGIN")
            anchor = anchor_id if anchor_id is not None else connection.execute(
                "SELECT COALESCE(MAX(id), 0) FROM state_snapshots"
            ).fetchone()[0]
            count = connection.execute("SELECT COUNT(*) FROM state_snapshots WHERE id <= ?", (anchor,)).fetchone()[0]
            page = min(page, max(0, (count - 1) // page_size))
            rows = connection.execute("""
                SELECT s.id AS state_id, s.started_at, s.finished_at,
                    m.cpu_percent, m.memory_percent, m.swap_percent,
                    p.skipped_count,
                    (SELECT COUNT(*) FROM process_metrics WHERE snapshot_id = p.id) AS process_count
                FROM state_snapshots s
                JOIN system_metrics m ON m.id = s.system_metric_id
                JOIN process_snapshots p ON p.id = s.process_snapshot_id
                WHERE s.id <= ? ORDER BY s.id DESC LIMIT ? OFFSET ?
            """, (anchor, page_size, page * page_size)).fetchall()
            return {"rows": [dict(row) for row in rows], "total": count,
                    "page": page, "page_size": page_size, "anchor_id": anchor,
                    "generation": self._generation(connection)}

    def clear(self, *, confirmed: bool = False) -> dict:
        if confirmed is not True:
            raise ValueError("Clearing state history requires confirmation")
        with self.database.connection() as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                count = connection.execute("SELECT COUNT(*) FROM state_snapshots").fetchone()[0]
                connection.execute("""CREATE TEMP TABLE removed_state_links AS
                    SELECT system_metric_id, process_snapshot_id FROM state_snapshots""")
                connection.execute("DELETE FROM state_snapshots")
                connection.execute("DELETE FROM process_snapshots WHERE id IN (SELECT process_snapshot_id FROM removed_state_links)")
                connection.execute("DELETE FROM system_metrics WHERE id IN (SELECT system_metric_id FROM removed_state_links)")
                connection.execute("""INSERT INTO app_metadata(key, value)
                    VALUES ('desktop_history_generation', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (str(uuid4()),))
        return {"deleted_count": count, "storage": self.info()}

    def open_folder(self) -> dict:
        folder = str(self.database.path.resolve().parent)
        if os.name == "nt":
            os.startfile(folder)
        else:
            executable = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.run([executable, folder], check=True, capture_output=True, timeout=10)
        return self.info()
