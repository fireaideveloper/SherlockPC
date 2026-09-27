import json
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone

import pytest

from sherlock.baseline import _json_default
from sherlock.capabilities.state.baseline import BaselineInput, BaselinePoint, build_baseline
from sherlock.capabilities.state.evidence import build_evidence


def report(cpu=90.0, count=31):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = tuple(BaselinePoint(i+1, start+timedelta(seconds=i*10),
                    10, 40, 4000, 6000, 0) for i in range(count))
    target = BaselinePoint(100, start+timedelta(seconds=400),
                           cpu, 40, 4000, 6000, 0)
    return build_evidence(build_baseline(BaselineInput(target, history, start,
                           target.timestamp, 200)))


def deviations(result):
    return [e for e in result.evidence if e.kind == 'baseline_deviation']


def test_high_cpu_has_traceable_sources_and_numeric_reference():
    result = report()
    evidence, = deviations(result)
    assert evidence.metric == 'cpu_percent'
    assert evidence.reference_p90 == 10
    assert evidence.delta_from_median == 80
    assert evidence.source_state_ids == (100, *range(1, 32))
    assert len({e.evidence_id for e in result.evidence}) == len(result.evidence)


@pytest.mark.parametrize('count', [0, 1, 29])
def test_insufficient_history_keeps_observations_without_deviation(count):
    result = report(count=count)
    assert result.baseline.status == 'insufficient_data'
    assert len(result.evidence) == 5
    assert deviations(result) == []


@pytest.mark.parametrize('cpu', [10, 20])
def test_normal_and_exact_threshold_are_not_flagged(cpu):
    assert deviations(report(cpu=cpu)) == []


def test_just_above_threshold_is_flagged():
    assert len(deviations(report(cpu=20.01))) == 1


def test_drop_is_preserved_without_fault_claim():
    original = report().baseline
    metrics = tuple(replace(m, current=0, p10=40, p90=40, median=40)
                    if m.name == 'cpu_percent' else m for m in original.metrics)
    evidence, = deviations(build_evidence(replace(original, metrics=metrics)))
    assert evidence.delta_from_median == -40
    assert 'below' in evidence.statement


def test_json_contains_provenance_and_version():
    payload = json.loads(json.dumps(asdict(report()), default=_json_default, allow_nan=False))
    assert payload['schema_version'] == '1.0'
    assert len(payload['baseline']['history_ids']) == 31
    assert payload['observed_at'].endswith('+00:00')


def test_cli_missing_database_does_not_create_file(tmp_path):
    path = tmp_path / 'missing.db'
    run = subprocess.run([sys.executable, '-m', 'sherlock.evidence',
                          '--state', '1', '--db', str(path)], capture_output=True, text=True)
    assert run.returncode != 0
    assert 'Database does not exist' in run.stderr
    assert not path.exists()
