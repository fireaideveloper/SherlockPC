from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from sherlock.capabilities.state.collector import StateCollector
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.investigation import InvestigationRequest, investigate
from sherlock.investigation.source import sqlite_source
from sherlock.storage.sqlite import Database
from sherlock.storage.sqlite.state_repository import StateRepository


_GIB = 1024 ** 3


class DesktopService:
    def __init__(
        self,
        database_path: str | Path,
        *,
        collector: StateCollector | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.database = Database(self.database_path)
        self.database.initialize()
        self.repository = StateRepository(self.database)
        self.collector = collector or StateCollector()

    def capture_state(self) -> dict[str, Any]:
        snapshot = self.collector.collect()
        state_id = self.repository.save(snapshot)
        return self._snapshot_payload(state_id, snapshot)

    def recent_states(self, limit: int = 6) -> list[dict[str, Any]]:
        if not 1 <= limit <= 50:
            raise ValueError("limit must be in [1, 50]")

        return [
            {
                "state_id": int(row["id"]),
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "cpu_percent": float(row["cpu_percent"]),
                "memory_percent": float(row["memory_percent"]),
                "process_count": int(row["process_count"]),
                "skipped_count": int(row["skipped_count"]),
            }
            for row in self.repository.recent(limit=limit)
        ]

    def investigate_current(
        self,
        question: str,
        *,
        hours: float = 24.0,
        limit: int = 200,
        min_samples: int = 30,
        min_span_seconds: float = 300.0,
    ) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        if len(question) > 500:
            raise ValueError("question is too long")

        current = self.capture_state()
        request = InvestigationRequest(
            state_id=current["state_id"],
            hours=hours,
            limit=limit,
            min_samples=min_samples,
            min_span_seconds=min_span_seconds,
        )
        report = investigate(request, sqlite_source(self.database_path))

        return {
            "question": question,
            "mode": "diagnose",
            "current": current,
            "report": asdict(report),
            "note": (
                "Desktop Alpha does not route natural language yet. "
                "The question is attached to a bounded CPU/RAM/swap investigation."
            ),
        }

    def overview(self) -> dict[str, Any]:
        current = self.capture_state()
        return {
            "current": current,
            "recent": self.recent_states(),
            "capabilities": {
                "diagnose": True,
                "search": False,
                "recall": False,
                "compare": False,
                "disk_health": False,
                "gpu_health": False,
            },
        }

    @staticmethod
    def _snapshot_payload(
        state_id: int,
        snapshot: StateSnapshot,
    ) -> dict[str, Any]:
        system = snapshot.system
        process_rows = sorted(
            snapshot.processes.processes,
            key=lambda item: item.memory_rss or 0,
            reverse=True,
        )[:5]

        return {
            "state_id": state_id,
            "started_at": snapshot.started_at.isoformat(),
            "finished_at": snapshot.finished_at.isoformat(),
            "system": {
                "timestamp": system.timestamp.isoformat(),
                "cpu_percent": system.cpu_percent,
                "memory_percent": system.memory_percent,
                "memory_used_gib": round(system.memory_used / _GIB, 3),
                "memory_available_gib": round(system.memory_available / _GIB, 3),
                "swap_percent": system.swap_percent,
                "disk_read_bytes": system.disk_read_bytes,
                "disk_write_bytes": system.disk_write_bytes,
                "network_rx_bytes": system.network_rx_bytes,
                "network_tx_bytes": system.network_tx_bytes,
            },
            "processes": {
                "count": len(snapshot.processes.processes),
                "skipped_count": snapshot.processes.skipped_count,
                "top_memory": [
                    {
                        "pid": process.pid,
                        "name": process.name or "unknown",
                        "status": process.status,
                        "memory_rss_gib": (
                            round(process.memory_rss / _GIB, 3)
                            if process.memory_rss is not None
                            else None
                        ),
                        "cpu_seconds": process.cpu_seconds,
                    }
                    for process in process_rows
                ],
            },
        }
