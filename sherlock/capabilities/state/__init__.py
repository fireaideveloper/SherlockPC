from dataclasses import dataclass
from datetime import datetime

from sherlock.capabilities.processes.models import ProcessSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric


@dataclass(frozen=True, slots=True)
class StateSnapshot:

    started_at: datetime
    finished_at: datetime

    system: SystemMetric
    processes: ProcessSnapshot

    def __post_init__(self) -> None:
        for value in (self.started_at, self.finished_at):
            if value.utcoffset() is None:
                raise ValueError(
                    "state timestamps must include a timezone"
                )
