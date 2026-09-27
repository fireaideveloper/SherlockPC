"""Traceable observations, not causal diagnoses or calibrated probabilities."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .baseline import BaselineReport


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    kind: Literal["observation", "baseline_deviation"]
    metric: str
    unit: str
    value: int | float
    source_state_ids: tuple[int, ...]
    statement: str
    reference_median: float | None = None
    reference_p10: float | None = None
    reference_p90: float | None = None
    delta_from_median: float | None = None
    rule: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceReport:
    schema_version: str
    rule_version: str
    target_id: int
    observed_at: datetime
    baseline: BaselineReport
    evidence: tuple[Evidence, ...]
    limitations: tuple[str, ...]


# Absolute tolerances in percentage points, deliberately explicit heuristics.
# These are initial engineering choices, not learned or validated thresholds.
TOLERANCES = {"cpu_percent": 10.0, "memory_percent": 5.0, "swap_percent": 5.0}


def build_evidence(baseline: BaselineReport) -> EvidenceReport:
    items: list[Evidence] = []
    for metric in baseline.metrics:
        items.append(Evidence(
            evidence_id=f"state-{baseline.target_id}:{metric.name}:observed",
            kind="observation", metric=metric.name, unit=metric.unit,
            value=metric.current, source_state_ids=(baseline.target_id,),
            statement=f"Observed {metric.name} = {metric.current} {metric.unit}.",
        ))
        tolerance = TOLERANCES.get(metric.name)
        if (baseline.status != "enough_data" or tolerance is None
                or metric.p10 is None or metric.p90 is None
                or metric.median is None):
            continue
        if metric.current > metric.p90 + tolerance:
            direction = "above"
            rule = f"current > historical_p90 + {tolerance} percentage_points"
        elif metric.current < metric.p10 - tolerance:
            direction = "below"
            rule = f"current < historical_p10 - {tolerance} percentage_points"
        else:
            continue
        items.append(Evidence(
            evidence_id=f"state-{baseline.target_id}:{metric.name}:deviation-v1",
            kind="baseline_deviation", metric=metric.name, unit=metric.unit,
            value=metric.current,
            source_state_ids=(baseline.target_id, *baseline.history_ids),
            statement=f"{metric.name} is {direction} the historical P10-P90 range beyond the tolerance.",
            reference_median=metric.median,
            reference_p10=metric.p10, reference_p90=metric.p90,
            delta_from_median=metric.current - metric.median, rule=rule,
        ))
    return EvidenceReport(
        schema_version="1.0", rule_version="baseline-tolerance-v1",
        target_id=baseline.target_id, observed_at=baseline.target_timestamp,
        baseline=baseline, evidence=tuple(items),
        limitations=(*baseline.warnings,
            "Deviation rules are unvalidated heuristics, not ML predictions.",
            "A deviation does not establish a fault, its cause, or a memory leak.",
            "No deviation does not establish that the computer is healthy.",
            "This report covers system metrics only; it does not attribute causes to processes."),
    )
