from dataclasses import dataclass
from typing import Literal

from .baseline import BaselineReport
from .evidence import Evidence, EvidenceReport, TOLERANCES, build_evidence


@dataclass(frozen=True, slots=True)
class AnomalyReport:
    schema_version: str
    status: Literal["anomalies_found", "no_anomalies_found", "insufficient_data"]
    evaluated_metrics: tuple[str, ...]
    anomalies: tuple[Evidence, ...]
    evidence_report: EvidenceReport


def detect_anomalies(baseline: BaselineReport) -> AnomalyReport:
    evidence = build_evidence(baseline)
    evaluated = tuple(
        metric.name for metric in baseline.metrics
        if baseline.status == "enough_data"
        and metric.name in TOLERANCES
        and metric.median is not None
        and metric.p10 is not None
        and metric.p90 is not None
    )
    anomalies = tuple(
        item for item in evidence.evidence
        if item.kind == "baseline_deviation"
    )
    if baseline.status == "insufficient_data" or not evaluated:
        status = "insufficient_data"
    elif anomalies:
        status = "anomalies_found"
    else:
        status = "no_anomalies_found"
    return AnomalyReport(
        schema_version="1.0", status=status,
        evaluated_metrics=evaluated, anomalies=anomalies,
        evidence_report=evidence,
    )
