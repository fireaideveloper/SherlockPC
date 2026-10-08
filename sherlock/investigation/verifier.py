"""Check provenance and rule support; never promote a signal to a proven cause."""
from sherlock.capabilities.state.evidence import EvidenceReport, build_evidence
from .investigator import RULES
from .critic import critique_hypotheses
from .reasoning_models import Critique, Hypothesis, Verdict


def verify_hypotheses(hypotheses: tuple[Hypothesis, ...], critiques: tuple[Critique, ...],
                      report: EvidenceReport) -> tuple[Verdict, ...]:
    # Rebuild canonical evidence from baseline to reject altered values, statements,
    # IDs and source lists. This is a consistency check, not independent measurement.
    canonical_report = build_evidence(report.baseline)
    canonical = {e.evidence_id: e for e in canonical_report.evidence}
    actual = {e.evidence_id: e for e in report.evidence}
    valid_report = (report == canonical_report and len(actual) == len(report.evidence))
    ids = [h.hypothesis_id for h in hypotheses]
    results = []
    for hypothesis in hypotheses:
        refs = hypothesis.evidence_ids
        rule = RULES.get(hypothesis.kind)
        matching_critiques = [c for c in critiques if c.hypothesis_id == hypothesis.hypothesis_id]
        valid_refs = bool(refs) and len(set(refs)) == len(refs) and all(
            ref in actual and actual[ref] == canonical.get(ref) for ref in refs)
        if (not valid_report or not rule or not valid_refs
                or ids.count(hypothesis.hypothesis_id) != 1
                or len(matching_critiques) != 1
                or tuple(matching_critiques) != critique_hypotheses((hypothesis,), report)):
            results.append(Verdict(hypothesis.hypothesis_id, 'REJECTED',
                'Missing, duplicated or inconsistent evidence, hypothesis or critique.', ()))
            continue
        metric, threshold, statement = rule
        expected_id = f'state-{report.target_id}:{hypothesis.kind}:v1'
        observations = [actual[ref] for ref in refs if actual[ref].kind == 'observation'
                        and actual[ref].metric == metric]
        if (hypothesis.statement != statement or hypothesis.hypothesis_id != expected_id
                or any(actual[ref].metric != metric for ref in refs)
                or len(observations) != 1):
            results.append(Verdict(hypothesis.hypothesis_id, 'REJECTED',
                'Claim or cited metric does not match the supported rule.', ()))
        elif observations[0].value < threshold:
            results.append(Verdict(hypothesis.hypothesis_id, 'INSUFFICIENT_EVIDENCE',
                f'Relative deviation does not meet the {metric} >= {threshold}% signal rule.', refs))
        else:
            results.append(Verdict(hypothesis.hypothesis_id, 'SUPPORTED_SIGNAL',
                f'Observed {metric} >= {threshold}%; the signal is supported, its causal role is not.', refs))
    return tuple(results)
