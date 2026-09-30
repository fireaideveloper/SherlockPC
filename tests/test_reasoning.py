from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys

import pytest

from sherlock.capabilities.state.baseline import BaselineInput, BaselinePoint, build_baseline
from sherlock.capabilities.state.evidence import build_evidence
from sherlock.investigation import InvestigationRequest, investigate
from sherlock.investigation.investigator import generate_hypotheses
from sherlock.investigation.critic import critique_hypotheses
from sherlock.investigation.verifier import verify_hypotheses


START = datetime(2026, 9, 29, tzinfo=timezone.utc)


class Source:
    def __init__(self, cpu=10, memory=40, swap=0, count=31, historical_cpu=10):
        target = BaselinePoint(100, START + timedelta(seconds=1000),
                               cpu, memory, 4000, 6000, swap)
        history = tuple(BaselinePoint(i + 1, START + timedelta(seconds=i * 10),
                                     historical_cpu, 40, 4000, 6000, 0)
                        for i in range(count))
        self.data = BaselineInput(target, history, START, target.timestamp, 200)

    def load(self, target_id, *, hours, limit):
        return self.data


def evaluate(**kwargs):
    evidence = build_evidence(build_baseline(Source(**kwargs).data))
    hypotheses = generate_hypotheses(evidence)
    critiques = critique_hypotheses(hypotheses, evidence)
    return evidence, hypotheses, critiques, verify_hypotheses(hypotheses, critiques, evidence)


@pytest.mark.parametrize('kwargs,kind', [
    ({'cpu': 85}, 'cpu_contention'), ({'memory': 85}, 'memory_pressure'),
    ({'swap': 10}, 'swap_usage'),
])
def test_exact_absolute_threshold_supports_signal_only(kwargs, kind):
    evidence, hypotheses, critiques, verdicts = evaluate(**kwargs)
    assert [h.kind for h in hypotheses] == [kind]
    assert verdicts[0].status == 'SUPPORTED_SIGNAL'
    assert not verdicts[0].cause_confirmed
    assert critiques[0].alternatives and critiques[0].missing_checks
    assert all(ref in {e.evidence_id for e in evidence.evidence} for ref in verdicts[0].evidence_ids)


@pytest.mark.parametrize('kwargs', [{'cpu': 84.99}, {'memory': 84.99}, {'swap': 9.99}, {'cpu': 21}])
def test_relative_deviation_is_not_absolute_pressure(kwargs):
    _, hypotheses, critiques, verdicts = evaluate(**kwargs)
    assert len(hypotheses) == 1
    assert verdicts[0].status == 'INSUFFICIENT_EVIDENCE'
    assert any('absolute' in objection for objection in critiques[0].objections)


def test_no_candidates_for_normal_or_downward_deviation():
    assert evaluate()[1] == ()
    assert evaluate(cpu=10, historical_cpu=40)[1] == ()


def test_constant_high_cpu_still_produces_signal_without_anomaly():
    report = investigate(InvestigationRequest(100), Source(cpu=90, historical_cpu=90))
    assert report.status == 'NO_ANOMALY_FOUND'
    assert report.reasoning.verdicts[0].status == 'SUPPORTED_SIGNAL'
    assert report.findings == ()


def test_insufficient_history_does_not_hide_absolute_observation():
    report = investigate(InvestigationRequest(100), Source(cpu=90, count=0))
    assert report.status == 'INSUFFICIENT_EVIDENCE'
    assert report.reasoning.verdicts[0].status == 'SUPPORTED_SIGNAL'
    assert any('baseline' in s for s in report.reasoning.critiques[0].objections)


def test_three_signals_are_bounded_and_not_ranked_as_causes():
    report = investigate(InvestigationRequest(100), Source(cpu=95, memory=95, swap=50))
    assert len(report.reasoning.hypotheses) == 3
    assert len(report.trace) == 8
    assert all(v.status == 'SUPPORTED_SIGNAL' and not v.cause_confirmed
               for v in report.reasoning.verdicts)
    assert 'No slowdown cause confirmed' in report.reasoning.summary


@pytest.mark.parametrize('tamper', ['id', 'statement', 'wrong_metric', 'no_refs', 'duplicate_refs',
                                  'missing_ref', 'unknown_kind'])
def test_verifier_rejects_unsupported_claims(tamper):
    evidence, hypotheses, _, _ = evaluate(cpu=90)
    h = hypotheses[0]
    changes = {
        'id': {'hypothesis_id': 'wrong'}, 'statement': {'statement': 'A process caused a slowdown.'},
        'wrong_metric': {'evidence_ids': ('state-100:memory_percent:observed',)},
        'no_refs': {'evidence_ids': ()}, 'duplicate_refs': {'evidence_ids': h.evidence_ids * 2},
        'missing_ref': {'evidence_ids': ('missing',)}, 'unknown_kind': {'kind': 'unknown'},
    }
    h = replace(h, **changes[tamper])
    verdict = verify_hypotheses((h,), critique_hypotheses((h,), evidence), evidence)[0]
    assert verdict.status == 'REJECTED'
    assert verdict.evidence_ids == ()


@pytest.mark.parametrize('tamper', ['value', 'sources', 'statement', 'duplicate', 'target'])
def test_verifier_rejects_corrupted_evidence(tamper):
    evidence, hypotheses, critiques, _ = evaluate(cpu=90)
    items = list(evidence.evidence)
    if tamper == 'duplicate':
        items.append(items[0])
    elif tamper == 'target':
        evidence = replace(evidence, target_id=999)
    else:
        field = {'value': {'value': 99}, 'sources': {'source_state_ids': (999,)},
                 'statement': {'statement': 'altered'}}[tamper]
        items[0] = replace(items[0], **field)
    evidence = replace(evidence, evidence=tuple(items))
    assert verify_hypotheses(hypotheses, critiques, evidence)[0].status == 'REJECTED'


@pytest.mark.parametrize('tamper', ['missing', 'duplicate', 'stripped'])
def test_verifier_requires_complete_critique(tamper):
    evidence, hypotheses, critiques, _ = evaluate(cpu=90)
    if tamper == 'missing':
        critiques = ()
    elif tamper == 'duplicate':
        critiques *= 2
    else:
        critiques = (replace(critiques[0], objections=(), missing_checks=()),)
    assert verify_hypotheses(hypotheses, critiques, evidence)[0].status == 'REJECTED'


def test_duplicate_hypotheses_are_rejected():
    evidence, hypotheses, critiques, _ = evaluate(cpu=90)
    verdicts = verify_hypotheses(hypotheses * 2, critiques, evidence)
    assert all(v.status == 'REJECTED' for v in verdicts)


def test_swap_critique_requires_activity_measurement():
    _, hypotheses, critiques, verdicts = evaluate(swap=30)
    assert 'active paging' in hypotheses[0].statement
    assert any('swap-in/swap-out' in s for s in critiques[0].missing_checks)
    assert any('inactive pages' in s for s in critiques[0].alternatives)
    assert not verdicts[0].cause_confirmed


def test_missing_data_does_not_generate_reasoning(tmp_path):
    result = subprocess.run([sys.executable, '-m', 'sherlock.investigate', '--state', '1',
                             '--db', str(tmp_path / 'absent.db'), '--json'],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['reasoning'] is None
