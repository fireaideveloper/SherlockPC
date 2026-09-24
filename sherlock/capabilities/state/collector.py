from datetime import datetime, timezone

from sherlock.capabilities.processes.collector import ProcessCollector
from sherlock.capabilities.telemetry.collector import TelemetryCollector

from .models import StateSnapshot


class StateCollector:

    def __init__(
        self,
        telemetry_collector: TelemetryCollector | None = None,
        process_collector: ProcessCollector | None = None,
    ) -> None:
        self.telemetry_collector = (
            telemetry_collector
            if telemetry_collector is not None
            else TelemetryCollector()
        )

        self.process_collector = (
            process_collector
            if process_collector is not None
            else ProcessCollector()
        )

    def collect(self) -> StateSnapshot:
        started_at = datetime.now(timezone.utc)

        system = self.telemetry_collector.collect()
        processes = self.process_collector.collect()

        return StateSnapshot(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            system=system,
            processes=processes,
        )
