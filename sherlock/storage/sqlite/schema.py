SCHEMA_VERSION = 3


MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    ),
    2: (
        """
        CREATE TABLE system_metrics (
            id INTEGER PRIMARY KEY,

            timestamp TEXT NOT NULL,

            cpu_percent REAL NOT NULL
                CHECK (cpu_percent BETWEEN 0 AND 100),

            memory_percent REAL NOT NULL
                CHECK (memory_percent BETWEEN 0 AND 100),

            memory_used INTEGER NOT NULL
                CHECK (memory_used >= 0),

            memory_available INTEGER NOT NULL
                CHECK (memory_available >= 0),

            swap_percent REAL NOT NULL
                CHECK (swap_percent BETWEEN 0 AND 100),

            disk_read_bytes INTEGER
                CHECK (disk_read_bytes >= 0),

            disk_write_bytes INTEGER
                CHECK (disk_write_bytes >= 0),

            network_rx_bytes INTEGER
                CHECK (network_rx_bytes >= 0),

            network_tx_bytes INTEGER
                CHECK (network_tx_bytes >= 0)
        )
        """,
        """
        CREATE INDEX idx_system_metrics_timestamp
        ON system_metrics (timestamp)
        """,
    ),
    3: (
        """
        CREATE TABLE process_snapshots (
            id INTEGER PRIMARY KEY,

            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,

            skipped_count INTEGER NOT NULL
                CHECK (skipped_count >= 0)
        )
        """,
        """
        CREATE TABLE process_metrics (
            id INTEGER PRIMARY KEY,

            snapshot_id INTEGER NOT NULL
                REFERENCES process_snapshots(id)
                ON DELETE CASCADE,

            observed_at TEXT NOT NULL,

            pid INTEGER NOT NULL
                CHECK (pid >= 0),

            create_time REAL NOT NULL,

            name TEXT,
            status TEXT,

            memory_rss INTEGER
                CHECK (memory_rss >= 0),

            cpu_seconds REAL
                CHECK (cpu_seconds >= 0),

            UNIQUE (snapshot_id, pid)
        )
        """,
        """
        CREATE INDEX idx_process_snapshots_started_at
        ON process_snapshots (started_at)
        """,
        """
        CREATE INDEX idx_process_metrics_identity
        ON process_metrics (pid, create_time, snapshot_id)
        """,
    ),
}
