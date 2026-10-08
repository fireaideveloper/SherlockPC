import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sherlock.storage.sqlite.baseline_reader import BaselineReader
from sherlock.storage.sqlite.database import Database


class _ReadOnlyDatabase(Database):
    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        # mode=ro also prevents silently creating an absent database.
        connection = sqlite3.connect(
            self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            yield connection
        finally:
            connection.close()


def sqlite_source(path: str | Path) -> BaselineReader:
    return BaselineReader(_ReadOnlyDatabase(path))
