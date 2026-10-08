"""Generate bounded candidates, not diagnoses or process accusations."""
from sherlock.capabilities.state.evidence import EvidenceReport
from .reasoning_models import Hypothesis


# Absolute thresholds are deliberately separate from relative anomaly rules.
# They are heuristics to be calibrated, not probabilities of a fault.
RULES = {
    'cpu_contention': ('cpu_percent', 85.0,
        'High CPU utilization may contribute to reduced responsiveness.'),
    'memory_pressure': ('memory_percent', 85.0,
        'High RAM utilization may indicate memory pressure.'),
    'swap_usage': ('swap_percent', 10.0,
        'Swap is occupied; active paging as a slowdown mechanism needs checking.'),
}


def generate_hypotheses(report: EvidenceReport) -> tuple[Hypothesis, ...]:
    candidates = []
    for kind, (metric, threshold, statement) in RULES.items():
        observations = [e for e in report.evidence
                        if e.kind == 'observation' and e.metric == metric]
        upward = [e for e in report.evidence
                  if e.kind == 'baseline_deviation' and e.metric == metric
                  and e.reference_p90 is not None and e.value > e.reference_p90]
        if observations and (observations[0].value >= threshold or upward):
            candidates.append(Hypothesis(
                hypothesis_id=f'state-{report.target_id}:{kind}:v1',
                kind=kind, statement=statement,
                evidence_ids=tuple(e.evidence_id for e in (*observations, *upward)),
            ))
    return tuple(candidates)
