from sherlock.capabilities.state.evidence import EvidenceReport
from .investigator import RULES
from .reasoning_models import Critique, Hypothesis


CHECKS = {
    'cpu_contention': (
        ('An expected game, build or computation may explain high CPU usage.',),
        ('Measure sustained CPU usage and responsiveness over time.',
         'Compare per-process CPU usage over the same interval.')),
    'memory_pressure': (
        ('Expected application allocations may explain high RAM usage.',),
        ('Measure available memory and paging activity over time.',
         'Check per-process memory growth; one snapshot cannot establish a leak.')),
    'swap_usage': (
        ('Swap may contain inactive pages retained from an earlier workload.',),
        ('Measure swap-in/swap-out rates or page faults over time.',
         'Correlate paging with disk latency and the reported slowdown.')),
}


def critique_hypotheses(hypotheses: tuple[Hypothesis, ...],
                        report: EvidenceReport) -> tuple[Critique, ...]:
    results = []
    for hypothesis in hypotheses:
        objections = ['A single snapshot does not establish a slowdown cause.']
        if hypothesis.kind not in RULES:
            results.append(Critique(hypothesis.hypothesis_id, (), (),
                                    ('Unknown hypothesis kind.',)))
            continue
        metric, threshold, _ = RULES[hypothesis.kind]
        observations = [e for e in report.evidence
                        if e.kind == 'observation' and e.metric == metric]
        if not observations or observations[0].value < threshold:
            objections.append('Relative deviation alone does not meet the absolute signal threshold.')
        if report.baseline.status == 'insufficient_data':
            objections.append('Historical baseline is insufficient; usual workload is unknown.')
        alternatives, missing = CHECKS[hypothesis.kind]
        results.append(Critique(hypothesis.hypothesis_id, alternatives, missing, tuple(objections)))
    return tuple(results)
