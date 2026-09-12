SCHEMA_VERSION = 2


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
}