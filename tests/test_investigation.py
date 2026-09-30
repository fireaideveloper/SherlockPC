import json
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from sherlock.capabilities.state.baseline import BaselineInput, BaselinePoint
from sherlock.capabilities.processes.models import ProcessSnapshot
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.investigation import InvestigationRequest, investigate
from sherlock.investigation.engine import _StateMachine
from sherlock.investigation.source import sqlite_source
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_repository import StateRepository


START = datetime(2026, 9, 29, tzinfo=timezone.utc)


class Source:
    def __init__(self, cpu=10, count=31, historical_cpu=10, memory=40, swap=0):
        self.calls = 0
        target = BaselinePoint(100, START + timedelta(seconds=1000),
                               cpu, memory, 4000, 6000, swap)
        history = tuple(BaselinePoint(i + 1, START + timedelta(seconds=i * 10),
                                     historical_cpu, 40, 4000, 6000, 0)
                        for i in range(count))
        self.data = BaselineInput(target, history, START, target.timestamp, 200)

    def load(self, target_id, *, hours, limit):
        self.calls += 1
        return self.data


@pytest.mark.parametrize("cpu,count,status", [
    (10, 31, "NO_ANOMALY_FOUND"), (90, 31, "ANOMALIES_FOUND"),
    (90, 0, "INSUFFICIENT_EVIDENCE"), (90, 29, "INSUFFICIENT_EVIDENCE"),
])
def test_cases_have_bounded_trace_and_one_read(cpu, count, status):
    source = Source(cpu=cpu, count=count)
    report = investigate(InvestigationRequest(100), source)
    assert report.status == status
    assert source.calls == 1
    assert [event.stage for event in report.trace] == [
        "UNDERSTAND", "PLAN", "COLLECT", "ANALYZE",
        "GENERATE_HYPOTHESES", "CRITIQUE", "VERIFY", "COMPLETE"]
    if status != "ANOMALIES_FOUND":
        assert report.findings == ()


def test_all_findings_have_traceable_sources_and_no_causal_claim():
    report = investigate(InvestigationRequest(100), Source(cpu=90, memory=80, swap=30))
    assert len(report.findings) == 3
    evidence = {item.evidence_id: item for item in report.anomaly_report.evidence_report.evidence}
    for finding in report.findings:
        for identifier in finding.evidence_ids:
            assert evidence[identifier].statement == finding.statement
            assert evidence[identifier].source_state_ids == (100, *range(1, 32))
    assert "cause has not been established" in report.conclusion


def test_lower_deviation_is_not_mislabelled_as_high_load():
    report = investigate(InvestigationRequest(100), Source(cpu=10, historical_cpu=40))
    assert report.status == "ANOMALIES_FOUND"
    assert "below" in report.findings[0].statement


@pytest.mark.parametrize("changes", [
    {"state_id": 0}, {"hours": float("nan")}, {"hours": float("inf")},
    {"hours": 8761}, {"limit": 2001}, {"min_samples": 1},
    {"limit": 20}, {"min_span_seconds": -1}, {"min_span_seconds": float("nan")},
])
def test_invalid_request(changes):
    with pytest.raises(ValueError):
        InvestigationRequest(**({"state_id": 100} | changes))


@pytest.mark.parametrize("change", ["target", "history", "limit"])
def test_invalid_source_never_produces_findings(change):
    source = Source()
    if change == "target":
        source.data = replace(source.data, target=replace(source.data.target, state_id=999))
    elif change == "limit":
        source.data = replace(source.data, limit=199)
    else:
        source.data = replace(source.data, history=(source.data.target,))
    report = investigate(InvestigationRequest(100), source)
    assert report.status == "DATA_UNAVAILABLE"
    assert report.findings == ()
    assert report.trace[-1].stage == "COMPLETE"


def test_illegal_and_terminal_transitions():
    machine = _StateMachine()
    with pytest.raises(RuntimeError):
        machine.move("VERIFY", "invalid")
    for stage in ("UNDERSTAND", "PLAN", "COLLECT", "COMPLETE"):
        machine.move(stage, "test")
    with pytest.raises(RuntimeError):
        machine.move("COLLECT", "must not retry")


def run_cli(path, *args):
    return subprocess.run([sys.executable, "-m", "sherlock.investigate", "--db", str(path),
                           "--json", *args], capture_output=True, text=True)


@pytest.mark.parametrize("kind", ["missing", "corrupt", "empty"])
def test_unavailable_database_returns_json_and_nonzero(tmp_path, kind):
    path = tmp_path / "source.db"
    if kind == "corrupt":
        path.write_bytes(b"not a sqlite database")
    elif kind == "empty":
        Database(path).initialize()
    result = run_cli(path, "--state", "1")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "DATA_UNAVAILABLE"
    assert payload["findings"] == []
    assert "Traceback" not in result.stderr
    if kind == "missing":
        assert not path.exists()


def test_readonly_source_and_cli_integration(tmp_path):
    path = tmp_path / "test #1.db"
    db = Database(path)
    db.initialize()
    repository = StateRepository(db)
    for index in range(32):
        moment = START + timedelta(seconds=index * 10)
        metric = SystemMetric(timestamp=moment + timedelta(seconds=1),
            cpu_percent=90 if index == 31 else 10, memory_percent=40,
            memory_used=4000, memory_available=6000, swap_percent=0,
            disk_read_bytes=None, disk_write_bytes=None,
            network_rx_bytes=None, network_tx_bytes=None)
        target = repository.save(StateSnapshot(started_at=moment,
            finished_at=moment + timedelta(seconds=3), system=metric,
            processes=ProcessSnapshot(started_at=moment, finished_at=moment,
                                      processes=(), skipped_count=0)))
    with sqlite_source(path).database.connection() as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM state_snapshots")
    before = path.read_bytes()
    result = run_cli(path, "--state", str(target))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ANOMALIES_FOUND"
    assert payload["schema_version"] == "1.1"
    assert payload["reasoning"]["hypotheses"][0]["kind"] == "cpu_contention"
    assert payload["reasoning"]["verdicts"][0]["status"] == "SUPPORTED_SIGNAL"
    assert payload["reasoning"]["verdicts"][0]["cause_confirmed"] is False
    assert payload["anomaly_report"]["evidence_report"]["baseline"]["sample_count"] == 31
    assert payload["findings"][0]["evidence_ids"] == [f"state-{target}:cpu_percent:deviation-v1"]
    assert path.read_bytes() == before
    result = run_cli(path, "--state", "9999")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "DATA_UNAVAILABLE"
    result = run_cli(path, "--state", str(target), "--hours", "nan")
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_verification_rejects_unsupported_finding(monkeypatch):
    from sherlock.investigation import engine
    real_detect = engine.detect_anomalies

    def broken_detect(baseline):
        report = real_detect(baseline)
        return replace(report, anomalies=(replace(report.anomalies[0], evidence_id="missing"),))

    monkeypatch.setattr(engine, "detect_anomalies", broken_detect)
    with pytest.raises(RuntimeError, match="evidence"):
        investigate(InvestigationRequest(100), Source(cpu=90))
