from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SystemMetric:

    timestamp: datetime

    cpu_percent: float

    memory_percent: float
    memory_used: int
    memory_available: int

    swap_percent: float

    disk_read_bytes: int | None
    disk_write_bytes: int | None

    network_rx_bytes: int | None
    network_tx_bytes: int | None

    def __post_init__(self) -> None:
        if self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
