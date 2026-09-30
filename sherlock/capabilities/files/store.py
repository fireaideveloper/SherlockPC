import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 1


@contextmanager
def connect(path: Path, *, readonly: bool = False):
    if readonly:
        connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        if readonly:
            connection.execute('PRAGMA query_only = ON')
        yield connection
    finally:
        connection.close()


def initialize(connection: sqlite3.Connection) -> None:
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables and 'file_index_meta' not in tables:
        raise ValueError('This is not a file index database; use a separate files.db')
    connection.execute('CREATE TABLE IF NOT EXISTS file_index_meta (version INTEGER NOT NULL)')
    versions = [r[0] for r in connection.execute('SELECT version FROM file_index_meta')]
    if not versions:
        connection.execute('INSERT INTO file_index_meta VALUES (?)', (SCHEMA_VERSION,))
    elif versions != [SCHEMA_VERSION]:
        raise ValueError('Unsupported file index schema version')
    connection.execute('''CREATE TABLE IF NOT EXISTS indexed_files (
        root TEXT NOT NULL, path TEXT NOT NULL, name TEXT NOT NULL,
        relative_path TEXT NOT NULL, size_bytes INTEGER NOT NULL,
        modified_ns INTEGER NOT NULL, changed_ns INTEGER NOT NULL,
        name_fold TEXT NOT NULL, path_fold TEXT NOT NULL,
        content TEXT, content_fold TEXT, content_status TEXT NOT NULL,
        indexed_at TEXT NOT NULL, PRIMARY KEY (root, path)
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS scan_roots (
        root TEXT PRIMARY KEY, scanned_at TEXT NOT NULL, status TEXT NOT NULL,
        policy_json TEXT NOT NULL
    )''')


def validate(connection: sqlite3.Connection) -> None:
    if [r[0] for r in connection.execute('SELECT version FROM file_index_meta')] != [SCHEMA_VERSION]:
        raise ValueError('Unsupported file index schema version')
