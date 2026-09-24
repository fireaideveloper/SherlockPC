from datetime import datetime, timezone

import psutil

from .models import ProcessMetric, ProcessSnapshot


class ProcessCollector:

    def collect(self) -> ProcessSnapshot:
        started_at = datetime.now(timezone.utc)

        metrics: list[ProcessMetric] = []
        skipped_count = 0

        for pid in psutil.pids():
            try:
                # A fresh object for this collection.
                process = psutil.Process(pid)

                create_time = process.create_time()

                if create_time is None or not process.is_running():
                    skipped_count += 1
                    continue

                info = process.as_dict(
                    attrs=[
                        "name",
                        "status",
                        "memory_info",
                        "cpu_times",
                    ],
                    ad_value=None,
                )

                # Discard observations if the original process has
                # disappeared or its PID has been reused.
                if not process.is_running():
                    skipped_count += 1
                    continue

                observed_at = datetime.now(timezone.utc)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                skipped_count += 1
                continue

            memory = info["memory_info"]
            cpu = info["cpu_times"]

            metrics.append(
                ProcessMetric(
                    observed_at=observed_at,
                    pid=pid,
                    create_time=create_time,
                    name=info["name"],
                    status=info["status"],
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
