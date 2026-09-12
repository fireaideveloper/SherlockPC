from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .schema import MIGRATIONS, SCHEMA_VERSION


class Database:
    """Manage SQLite connections and schema migrations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_info (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        version INTEGER NOT NULL
                    )
                    """
                )

                row = connection.execute(
                    """
                    SELECT version
                    FROM schema_info
                    WHERE id = 1
                    """
                ).fetchone()

                current_version = (
                    int(row["version"]) if row is not None else 0
                )

                if not 0 <= current_version <= SCHEMA_VERSION:
                    raise RuntimeError(
                        "Unsupported database schema version: "
                        f"{current_version}. "
                        f"This application supports up to {SCHEMA_VERSION}."
                    )

                for version in range(
                    current_version + 1,
                    SCHEMA_VERSION + 1,
                ):
                    for statement in MIGRATIONS[version]:
                        connection.execute(statement)

                    connection.execute(
                        """
                        INSERT INTO schema_info (id, version)
                        VALUES (1, ?)
                        ON CONFLICT(id)
                        DO UPDATE SET version = excluded.version
                        """,
                        (version,),
                    )

                connection.commit()

            except BaseException:
                connection.rollback()
                raise

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Open a connection; callers manage commit and rollback."""

        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row

        try:
            self._configure(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _configure(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")

    def get_schema_version(self) -> int | None:
        """Read the schema version after initialization."""

        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT version
                FROM schema_info
                WHERE id = 1
                """
            ).fetchone()

        if row is None:
            return None

        return int(row["version"])