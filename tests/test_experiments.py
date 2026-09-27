import csv
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from sherlock.capabilities.processes.models import ProcessMetric, ProcessSnapshot
from sherlock.capabilities.state.models import StateSnapshot
from sherlock.capabilities.telemetry.models import SystemMetric
from sherlock.record_experiment import FIELDS, record_experiment


class Clock:
    now = 0
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class Collector:
    def __init__(self, clock, error=None, latency=1):
        self.clock, self.error, self.latency = clock, error, latency
        self.calls = 0
    def collect(self):
        self.calls += 1
        if self.error and self.calls == 2:
            raise self.error
        self.clock.sleep(self.latency)
        now = datetime.now(timezone.utc)
        system = SystemMetric(now, 10, 40, 4000, 6000, 0, None, None, None, None)
        process = ProcessMetric(now, 123, 1.0, 'SECRET_USER_FILE.exe', 'running', 100, 2.0)
        return StateSnapshot(now, now, system, ProcessSnapshot(now, now, (process,), 2))


def run(tmp_path, error=None, latency=1):
    clock = Clock()
    return record_experiment(output=tmp_path, scenario='normal', machine_id='pc-01',
        session_id='s-01', duration=10, interval=5, collector=Collector(clock, error, latency),
        clock=clock, sleep=clock.sleep)


def test_recording_has_monotonic_timing_and_allowlisted_fields(tmp_path):
    folder, meta = run(tmp_path)
    rows = list(csv.DictReader((folder/'samples.csv').open()))
    assert meta['status'] == 'completed'
    assert meta['sample_count'] == 2
    assert [float(r['elapsed_seconds']) for r in rows] == [0, 5]
    assert tuple(rows[0]) == FIELDS
    assert rows[0]['skipped_process_count'] == '2'
    assert 'SECRET' not in (folder/'samples.csv').read_text()
    assert 'pid' not in rows[0]
    assert json.loads((folder/'metadata.json').read_text())['origin'] == 'real_measurement'


def test_interruption_preserves_completed_rows(tmp_path):
    folder, meta = run(tmp_path, KeyboardInterrupt())
    assert meta['status'] == 'interrupted'
    assert meta['sample_count'] == 1
    assert len(list(csv.DictReader((folder/'samples.csv').open()))) == 1


def test_failure_marks_run_without_exposing_exception_text(tmp_path):
    with pytest.raises(RuntimeError):
        run(tmp_path, RuntimeError('SECRET_PATH'))
    meta = json.loads(next(tmp_path.glob('*/metadata.json')).read_text())
    assert meta['status'] == 'failed'
    assert meta['sample_count'] == 1
    assert 'SECRET_PATH' not in json.dumps(meta)


def test_slow_collection_does_not_catch_up_in_bursts(tmp_path):
    folder, meta = run(tmp_path, latency=6)
    rows = list(csv.DictReader((folder/'samples.csv').open()))
    assert [float(r['elapsed_seconds']) for r in rows] == [0, 6]
    assert meta['elapsed_seconds'] == 12


@pytest.mark.parametrize('duration,interval', [(0,5),(10,0),(1,5),(float('nan'),5),(10,float('inf'))])
def test_invalid_timing_creates_no_run(tmp_path,duration,interval):
    with pytest.raises(ValueError):
        record_experiment(output=tmp_path,scenario='normal',machine_id='pc-01',session_id='s-01',
                          duration=duration,interval=interval)
    assert list(tmp_path.iterdir()) == []


def test_repeated_runs_are_distinct(tmp_path):
    first, _ = run(tmp_path)
    second, _ = run(tmp_path)
    assert first != second
