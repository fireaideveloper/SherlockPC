import json
from datetime import datetime, timezone

import pytest

from sherlock.capabilities.processes.models import ProcessMetric, ProcessSnapshot
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.desktop.service import DesktopService
from sherlock.desktop_bridge import _request_from_args, default_database_path, handle_request


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class FakeCollector:
    def collect(self):
        metric = SystemMetric(
            timestamp=NOW,
            cpu_percent=42.5,
            memory_percent=68.0,
            memory_used=8 * 1024 ** 3,
            memory_available=4 * 1024 ** 3,
            swap_percent=3.0,
            disk_read_bytes=123,
            disk_write_bytes=456,
            network_rx_bytes=789,
            network_tx_bytes=1011,
        )
        processes = ProcessSnapshot(
            started_at=NOW,
            finished_at=NOW,
            processes=(
                ProcessMetric(NOW, 20, 2.0, "small.exe", "running", 128 * 1024 ** 2, 4.0),
                ProcessMetric(NOW, 10, 1.0, "large.exe", "running", 2 * 1024 ** 3, 7.0),
            ),
            skipped_count=1,
        )
        return StateSnapshot(NOW, NOW, metric, processes)


def make_service(tmp_path):
    return DesktopService(tmp_path / "sherlock.db", collector=FakeCollector())


def test_capture_state_saves_real_snapshot_shape(tmp_path):
    service = make_service(tmp_path)
    result = service.capture_state()

    assert result["state_id"] == 1
    assert result["system"]["cpu_percent"] == 42.5
    assert result["system"]["memory_used_gib"] == 8.0
    assert result["processes"]["count"] == 2
    assert result["processes"]["skipped_count"] == 1
    assert result["processes"]["top_memory"][0]["name"] == "large.exe"
    assert service.recent_states()[0]["state_id"] == 1


def test_investigate_current_is_bounded_and_honest_with_no_history(tmp_path):
    service = make_service(tmp_path)
    result = service.investigate_current("Почему компьютер тормозит?")

    assert result["mode"] == "diagnose"
    assert result["report"]["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["report"]["trace"][0]["stage"] == "UNDERSTAND"
    assert result["report"]["trace"][-1]["stage"] == "COMPLETE"
    assert "does not route natural language" in result["note"]


def test_bridge_allows_only_named_actions(tmp_path):
    service = make_service(tmp_path)
    ping = handle_request({"action": "ping"}, service=service)
    assert ping["bridge"] == "desktop-bridge-v2"

    with pytest.raises(ValueError, match="unsupported desktop action"):
        handle_request({"action": "run_shell"}, service=service)


def test_bridge_overview_payload_is_json_serializable(tmp_path):
    service = make_service(tmp_path)
    payload = handle_request({"action": "overview"}, service=service)
    json.dumps(payload, allow_nan=False)


def test_bridge_investigation_payload_is_json_serializable(tmp_path):
    service = make_service(tmp_path)
    payload = handle_request(
        {"action": "investigate", "question": "Почему компьютер тормозит?"},
        service=service,
    )
    json.dumps(payload, allow_nan=False, default=lambda value: value.isoformat())
    assert payload["report"]["status"] == "INSUFFICIENT_EVIDENCE"



def test_bridge_accepts_sidecar_request_json_argument():
    payload = _request_from_args(["--request-json", '{"action":"ping"}'])
    assert payload == {"action": "ping"}


def test_bridge_rejects_unknown_sidecar_arguments():
    with pytest.raises(ValueError, match="unsupported arguments"):
        _request_from_args(["--not-allowed", "value"])


def test_default_database_path_uses_override(monkeypatch, tmp_path):
    expected = tmp_path / "custom.db"
    monkeypatch.setenv("SHERLOCK_DB_PATH", str(expected))
    assert default_database_path() == expected


def test_periodic_captures_build_history_without_questions(tmp_path):
    from dataclasses import replace
    from datetime import timedelta

    class TickingCollector(FakeCollector):
        tick = 0

        def collect(self):
            snapshot = super().collect()
            observed = NOW + timedelta(seconds=self.tick * 10)
            self.tick += 1
            return replace(snapshot, started_at=observed, finished_at=observed,
                           system=replace(snapshot.system, timestamp=observed),
                           processes=replace(snapshot.processes, started_at=observed,
                                             finished_at=observed))

    service = DesktopService(tmp_path / "auto.db", collector=TickingCollector())
    for _ in range(31):
        overview = service.overview()
    assert overview["history"]["sample_count"] == 30
    assert overview["history"]["span_seconds"] == 290
    assert overview["history"]["status"] == "insufficient_data"
    overview = service.overview()
    assert overview["history"]["sample_count"] == 31
    assert overview["history"]["span_seconds"] == 300
    assert overview["history"]["largest_gap_seconds"] == 10
    assert overview["history"]["status"] == "enough_data"
    report = service.investigate_current("CPU pressure?")["report"]
    assert report["status"] != "INSUFFICIENT_EVIDENCE"
    assert report["anomaly_report"]["evidence_report"]["baseline"]["sample_count"] == 32
