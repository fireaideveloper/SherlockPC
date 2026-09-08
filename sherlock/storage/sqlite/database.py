from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

from .schema import INITIAL_SCHEMA, SCHEMA_VERSION


class Database:
    """
    Local SQLite storage used by SherlockPC.

    The Database class is responsible only for:
    - opening SQLite connections;
    - configuring SQLite;
    - initializing the schema;
    - exposing safe connection contexts.

    Higher-level repositories will be added later.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        """
        Create the database and initialize the current schema.
        """

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.connection() as connection:
            connection.executescript(INITIAL_SCHEMA)

            connection.execute(
                """
                INSERT INTO schema_info (id, version)
                VALUES (1, ?)
                ON CONFLICT(id)
                DO UPDATE SET version = excluded.version
                """,
                (SCHEMA_VERSION,),
            )

            connection.commit()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """
        Open a configured SQLite connection.
        """

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
        """
        Configure SQLite for SherlockPC.
        """

        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        connection.execute(
            "PRAGMA journal_mode = WAL;"
        )

        connection.execute(
            "PRAGMA synchronous = NORMAL;"
        )

        connection.execute(
            "PRAGMA busy_timeout = 5000;"
        )

    def get_schema_version(self) -> int | None:
        """
        Return the currently stored schema version.
        """

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
