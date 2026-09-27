from datetime import datetime, timezone

import psutil

from .models import ProcessMetric, ProcessSnapshot


class ProcessCollector:

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def collect(self) -> ProcessSnapshot:
        started_at = datetime.now(timezone.utc)

        metrics: list[ProcessMetric] = []
        skipped_count = 0

        for pid in psutil.pids():
            try:
                process = psutil.Process(pid)

                create_time = process.create_time()

                if create_time is None or not process.is_running():
                    skipped_count += 1
                    continue

                info = process.as_dict(
                    attrs=(
                        ["name", "status", "memory_info", "cpu_times"]
                        if self.include_details else ["memory_info"]
                    ),
                    ad_value=None,
                )

                if not process.is_running():
                    skipped_count += 1
                    continue

                observed_at = datetime.now(timezone.utc)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                skipped_count += 1
                continue

            memory = info["memory_info"]
            cpu = info.get("cpu_times")

            metrics.append(
                ProcessMetric(
                    observed_at=observed_at,
                    pid=pid,
                    create_time=create_time,
                    name=info.get("name"),
                    status=info.get("status"),
                    memory_rss=(
                        memory.rss if memory is not None else None
                    ),
                    cpu_seconds=(
                        cpu.user + cpu.system
                        if cpu is not None
                        else None
                    ),
                )
            )

        return ProcessSnapshot(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            processes=tuple(metrics),
            skipped_count=skipped_count,
        )
