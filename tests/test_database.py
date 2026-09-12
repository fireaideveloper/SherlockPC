import sqlite3

import pytest

from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.schema import MIGRATIONS, SCHEMA_VERSION


def test_database_initialization(tmp_path):
    database_path = tmp_path / "nested" / "test.db"
    database = Database(database_path)

    database.initialize()

    assert database_path.exists()
    assert database.get_schema_version() == SCHEMA_VERSION

    with database.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM system_metrics"
        ).fetchone()[0]

    assert count == 0


def test_migration_from_version_one_preserves_data(tmp_path):
    database_path = tmp_path / "test.db"

    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE schema_info (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            );

            INSERT INTO schema_info VALUES (1, 1);

            CREATE TABLE app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT INTO app_metadata
            VALUES ('example', 'keep me');
            """
        )
        connection.commit()
    finally:
        connection.close()

    database = Database(database_path)

    database.initialize()
    database.initialize()

    assert database.get_schema_version() == SCHEMA_VERSION

    with database.connection() as connection:
        row = connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("example",),
        ).fetchone()

        connection.execute("SELECT * FROM system_metrics")

    assert row["value"] == "keep me"


def test_newer_schema_is_not_overwritten(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()

    with database.connection() as connection:
        connection.execute(
            "UPDATE schema_info SET version = ? WHERE id = 1",
            (SCHEMA_VERSION + 1,),
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="Unsupported"):
        database.initialize()

    assert database.get_schema_version() == SCHEMA_VERSION + 1


def test_failed_migration_is_rolled_back(tmp_path, monkeypatch):
    database = Database(tmp_path / "test.db")

    with database.connection() as connection:
        connection.executescript(
            """
            CREATE TABLE schema_info (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            );

            INSERT INTO schema_info VALUES (1, 1);

            CREATE TABLE app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        connection.commit()

    monkeypatch.setitem(
        MIGRATIONS,
        2,
        MIGRATIONS[2] + ("INVALID SQL",),
    )

    with pytest.raises(sqlite3.OperationalError):
        database.initialize()

    assert database.get_schema_version() == 1

    with database.connection() as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'system_metrics'
            """
        ).fetchone()

    assert row is None