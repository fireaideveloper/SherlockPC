from datetime import datetime, timezone

import psutil

from .models import SystemMetric


class TelemetryCollector:
    """Read system metrics without writing to storage."""

    def collect(self) -> SystemMetric:
        # A blocking measurement avoids the meaningless first
        # non-blocking CPU reading.
        cpu_percent = psutil.cpu_percent(interval=1.0)

        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Optional sources may be unavailable on some systems.
        try:
            disk = psutil.disk_io_counters()
        except (OSError, psutil.Error):
            disk = None

        try:
            network = psutil.net_io_counters()
        except (OSError, psutil.Error):
            network = None

        return SystemMetric(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used=memory.used,
            memory_available=memory.available,
            swap_percent=swap.percent,
            disk_read_bytes=(
                disk.read_bytes if disk is not None else None
            ),
            disk_write_bytes=(
                disk.write_bytes if disk is not None else None
            ),
            network_rx_bytes=(
                network.bytes_recv if network is not None else None
            ),
            network_tx_bytes=(
                network.bytes_sent if network is not None else None
            ),
        )