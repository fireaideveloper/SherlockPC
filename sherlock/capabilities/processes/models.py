from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProcessMetric:

    observed_at: datetime

    pid: int
    create_time: float

    name: str | None
    status: str | None

    memory_rss: int | None
    cpu_seconds: float | None

    def __post_init__(self) -> None:
        if self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")


@dataclass(frozen=True, slots=True)
class ProcessSnapshot:

    started_at: datetime
    finished_at: datetime

    processes: tuple[ProcessMetric, ...]
    skipped_count: int

    def __post_init__(self) -> None:
        for value in (self.started_at, self.finished_at):
            if value.utcoffset() is None:
                raise ValueError(
                    "snapshot timestamps must include a timezone"
                )

        if self.skipped_count < 0:
            raise ValueError("skipped_count must not be negative")