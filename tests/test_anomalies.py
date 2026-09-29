import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from sherlock.capabilities.state.anomalies import detect_anomalies
from sherlock.capabilities.state.baseline import BaselineInput, BaselinePoint, build_baseline
from sherlock.capabilities.processes.models import ProcessSnapshot
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.storage.sqlite.database import Database
from sherlock.storage.sqlite.state_repository import StateRepository


START = datetime(2026, 9, 29, tzinfo=timezone.utc)


def baseline(cpu=10, count=31, step=10, memory=40, swap=0, historical_cpu=10):
    history = tuple(BaselinePoint(i + 1, START + timedelta(seconds=i * step),
                                 historical_cpu, 40, 4000, 6000, 0)
                    for i in range(count))
    target = BaselinePoint(100, START + timedelta(seconds=1000),
                           cpu, memory, 4000, 6000, swap)
    return build_baseline(BaselineInput(target, history, START, target.timestamp, 200))


@pytest.mark.parametrize('cpu,status', [(10, 'no_anomalies_found'),
    (20, 'no_anomalies_found'), (20.01, 'anomalies_found'), (90, 'anomalies_found')])
def test_cpu_boundaries(cpu, status):
    assert detect_anomalies(baseline(cpu=cpu)).status == status


@pytest.mark.parametrize('count,step', [(0, 10), (1, 10), (29, 10), (31, 1)])
def test_insufficient_is_not_normal(count, step):
    report = detect_anomalies(baseline(cpu=90, count=count, step=step))
    assert report.status == 'insufficient_data'
    assert report.evaluated_metrics == ()
    assert report.anomalies == ()


def test_multiple_deviations_retain_evidence_and_sources():
    report = detect_anomalies(baseline(cpu=90, memory=80, swap=30))
    assert {a.metric for a in report.anomalies} == {'cpu_percent', 'memory_percent', 'swap_percent'}
    for anomaly in report.anomalies:
        assert anomaly in report.evidence_report.evidence
        assert anomaly.source_state_ids == (100, *range(1, 32))
        assert anomaly.rule is not None


def test_low_cpu_and_exact_lower_boundary():
    assert detect_anomalies(baseline(cpu=30, historical_cpu=40)).status == 'no_anomalies_found'
    report = detect_anomalies(baseline(cpu=29.99, historical_cpu=40))
    assert report.status == 'anomalies_found'
    assert 'below' in report.anomalies[0].statement


def test_uncovered_metric_is_not_claimed_as_evaluated():
    report = detect_anomalies(baseline())
    assert set(report.evaluated_metrics) == {'cpu_percent', 'memory_percent', 'swap_percent'}


def run_cli(path, *args):
    return subprocess.run([sys.executable, '-m', 'sherlock.anomalies', '--db', str(path),
                           *args], capture_output=True, text=True)


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    result = run_cli(path, '--state', '1')
    assert result.returncode != 0
    assert 'Database does not exist' in result.stderr
    assert not path.exists()


def test_cli_sqlite_to_json_and_no_data_mutation(tmp_path):
    path = tmp_path / 'test.db'
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
    before = path.read_bytes()
    result = run_cli(path, '--state', str(target), '--json')
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['status'] == 'anomalies_found'
    assert payload['anomalies'][0]['metric'] == 'cpu_percent'
    assert payload['evidence_report']['baseline']['sample_count'] == 31
    assert path.read_bytes() == before
    for extra in [('--state', '9999'), ('--state', str(target), '--hours', 'nan'),
                  ('--state', str(target), '--min-samples', '1')]:
        failed = run_cli(path, *extra)
        assert failed.returncode != 0
        assert 'Traceback' not in failed.stderr
